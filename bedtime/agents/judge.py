"""LLM judge: 7-dimension rubric, N samples, median per dimension.

The judge gets the deterministic measurements and is told to trust them over
its own impression. It never sees its previous scores.
"""

from __future__ import annotations

import statistics
from typing import Dict, List, Optional, Tuple

from ..errors import ProviderError, StructuredOutputError
from ..guardrails.humanity import rhythm_variance
from ..observability.metrics import METRICS
from ..prompts import JUDGE_SYSTEM, JUDGE_USER
from ..schemas import (
    RUBRIC_DIMENSIONS,
    Assessment,
    DeterministicReport,
    JudgeVerdict,
    StoryBrief,
)
from .base import Agent

_JUDGE_SCHEMA_HINT = (
    '{"scores": {"age_appropriateness": {"score": 1-5, "justification": "..."}, '
    '"narrative_arc": {...}, "engagement": {...}, "language_fit": {...}, '
    '"human_voice": {...}, "bedtime_suitability": {...}, "prompt_adherence": {...}}, '
    '"safety_violation": true|false, "safety_notes": "", '
    '"must_fix": ["..."], "strengths": ["..."], "overall_comment": "..."}'
)


class Judge(Agent):
    stage = "judge"

    def assess(
        self,
        story: str,
        brief: StoryBrief,
        deterministic: DeterministicReport,
        samples: Optional[int] = None,
    ) -> Assessment:
        """Score a story. Falls back to deterministic-only if the judge is down."""
        n = samples if samples is not None else self.settings.gate.judge_samples
        verdicts, failures = self._collect(story, brief, deterministic, n)

        if not verdicts:
            # Judge fully unavailable. Fall back to the deterministic signal
            # alone and mark the run degraded - never silently "pass".
            METRICS.inc("judge_unavailable_total")
            if self.trace is not None:
                self.trace.event("judge_unavailable", failures="; ".join(failures)[:200])
            return self._deterministic_only(deterministic, failures)

        assessment = self._aggregate(verdicts, deterministic)
        assessment.n_samples = len(verdicts)
        self._apply_gate(assessment, deterministic)

        METRICS.observe("story_quality_score", assessment.composite)
        METRICS.observe("judge_disagreement", round(1.0 - assessment.agreement, 4))
        if self.trace is not None:
            self.trace.event(
                "judged",
                composite=round(assessment.composite, 1),
                llm=round(assessment.llm_score, 1),
                deterministic=round(assessment.deterministic_score, 1),
                agreement=round(assessment.agreement, 3),
                samples=len(verdicts),
                passed=assessment.passed,
                must_fix=len(assessment.must_fix),
            )
        return assessment

    # -- sampling -----------------------------------------------------------
    def _collect(
        self, story: str, brief: StoryBrief, det: DeterministicReport, n: int
    ):
        must_include = (
            f"Explicit requirements: {'; '.join(brief.must_include)}\n"
            if brief.must_include else ""
        )
        user = JUDGE_USER.format(
            request=brief.sanitized_request,
            must_include=must_include,
            word_count=det.word_count,
            sentence_count=det.sentence_count,
            mean_sentence_words=det.mean_sentence_words,
            max_sentence_words=det.max_sentence_words,
            fk_grade=det.fk_grade,
            complex_word_ratio=det.complex_word_ratio,
            dialogue_ratio=det.dialogue_ratio,
            ends_calmly=det.ends_calmly,
            rhythm_variance=rhythm_variance(story),
            ai_tells="; ".join(det.ai_tells[:6]) or "none detected",
            story=story,
        )

        # TODO: these 3 samples are independent but run sequentially - most of
        # the end-to-end latency. asyncio.gather would fix it.
        verdicts: List[JudgeVerdict] = []
        failures: List[str] = []
        for i in range(max(1, n)):
            try:
                verdict, _ = self.structured_call(
                    JUDGE_SYSTEM,
                    user,
                    JudgeVerdict,
                    # Small temperature ladder decorrelates the samples. All
                    # stay low: we want independent opinions, not creativity.
                    temperature=min(0.6, self.settings.judge_temperature + 0.1 * i),
                    max_tokens=self.settings.max_tokens_judge,
                    schema_hint=_JUDGE_SCHEMA_HINT,
                    seed=1000 + i,
                )
                verdicts.append(verdict)
            except (ProviderError, StructuredOutputError) as exc:
                failures.append(f"sample{i}:{type(exc).__name__}")
                METRICS.inc("judge_sample_failures_total", error=type(exc).__name__)
                # One bad sample is survivable; give up only if all fail.
                continue
        return verdicts, failures

    # -- aggregation --------------------------------------------------------
    def _aggregate(self, verdicts: List[JudgeVerdict], det: DeterministicReport):
        medians: Dict[str, float] = {}
        spreads: Dict[str, float] = {}
        for dim in RUBRIC_DIMENSIONS:
            values = [v.scores[dim].score for v in verdicts if dim in v.scores]
            if not values:
                medians[dim], spreads[dim] = 3.0, 0.0
                continue
            medians[dim] = round(statistics.median(values), 3)
            spreads[dim] = round(max(values) - min(values), 3) if len(values) > 1 else 0.0

        llm_score = sum(medians[d] * w for d, w in RUBRIC_DIMENSIONS.items())
        llm_score = (llm_score - 1.0) / 4.0 * 100.0  # 1-5 -> 0-100

        # Agreement: 1.0 = every sample identical. Normalised by the 4-point
        # range of the scale so it reads as a percentage.
        mean_spread = statistics.mean(spreads.values()) if spreads else 0.0
        agreement = round(max(0.0, 1.0 - mean_spread / 4.0), 4)

        # Safety is a union, not a vote: if any judge saw a problem, we treat
        # the story as suspect. Cheap to regenerate, expensive to get wrong.
        flags = [v.safety_violation for v in verdicts]
        majority = sum(flags) > len(flags) / 2
        safety = any(flags) if self.settings.strict_safety else majority

        gate = self.settings.gate
        # Deterministic half is readability plus the machine-writing detector.
        det_score = 0.6 * det.readability_score + 0.4 * det.human_voice_score
        composite = gate.llm_weight * llm_score + gate.deterministic_weight * det_score

        return Assessment(
            composite=round(composite, 2),
            llm_score=round(llm_score, 2),
            deterministic_score=round(det_score, 2),
            dimension_medians=medians,
            dimension_spread=spreads,
            agreement=agreement,
            safety_violation=safety,
            must_fix=self._rank_fixes(verdicts),
            strengths=self._dedupe([s for v in verdicts for s in v.strengths])[:4],
            deterministic=det,
        )

    @staticmethod
    def _rank_fixes(verdicts: List[JudgeVerdict]):
        counts: Dict[str, int] = {}
        first_seen: Dict[str, int] = {}
        text: Dict[str, str] = {}
        for v in verdicts:
            for i, fix in enumerate(v.must_fix):
                key = fix.strip()
                if not key:
                    continue
                norm = key.lower()[:60]
                counts[norm] = counts.get(norm, 0) + 1
                first_seen[norm] = min(first_seen.get(norm, i), i)
                # Keep the most specific (longest) phrasing of an agreed fix.
                if len(key) > len(text.get(norm, "")):
                    text[norm] = key
        ranked = sorted(counts.items(), key=lambda kv: (-kv[1], first_seen.get(kv[0], 99)))
        return [text[k] for k, _ in ranked][:5]

    @staticmethod
    def _dedupe(items: List[str]):
        seen, out = set(), []
        for item in items:
            key = item.strip().lower()[:50]
            if key and key not in seen:
                seen.add(key)
                out.append(item.strip())
        return out

    # -- gating -------------------------------------------------------------
    def _apply_gate(self, a: Assessment, det: DeterministicReport) -> None:
        gate = self.settings.gate
        reasons: List[str] = []

        if a.safety_violation:
            reasons.append("judge flagged a safety violation")
        if det.banned_terms:
            reasons.append(f"banned terms: {', '.join(det.banned_terms[:3])}")
        low = [(d, s) for d, s in a.dimension_medians.items() if s < gate.min_dimension_score]
        for dim, score in low:
            reasons.append(f"{dim} scored {score} (floor {gate.min_dimension_score})")
        if det.human_voice_score < 65.0:
            reasons.append(
                f"reads as machine-written (human-voice {det.human_voice_score:.0f}/100): "
                + "; ".join(det.ai_tells[:2]))
        if a.composite < gate.accept_threshold:
            reasons.append(
                f"composite {a.composite:.1f} below threshold {gate.accept_threshold:.1f}")
        for f in det.failures:
            reasons.append(f)

        a.fail_reasons = reasons
        a.passed = not reasons
        if not a.passed:
            METRICS.inc("gate_failures_total", reason=_primary_reason(reasons))

    def _deterministic_only(self, det: DeterministicReport, failures: List[str]):
        a = Assessment(
            composite=round(det.readability_score * 0.6, 2),  # heavily discounted
            llm_score=0.0,
            deterministic_score=det.readability_score,
            agreement=0.0,
            deterministic=det,
            n_samples=0,
            fail_reasons=["judge unavailable: " + "; ".join(failures)[:120]] + det.failures,
        )
        a.passed = False
        return a


def _primary_reason(reasons: List[str]):
    if not reasons:
        return "none"
    first = reasons[0].lower()
    for needle, tag in (
        ("safety", "safety"), ("banned", "banned_terms"), ("composite", "below_threshold"),
        ("scary", "scary"), ("calm", "not_calm"), ("reading level", "reading_level"),
        ("sentences too long", "sentence_length"), ("scored", "dimension_floor"),
        ("judge unavailable", "judge_unavailable"),
    ):
        if needle in first:
            return tag
    return "other"
