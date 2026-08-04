"""Final gate before a story is returned.

Deterministic checks, the moderation API and the judge's safety flag can each
veto independently. If everything fails we serve FALLBACK_STORY.
"""

from typing import Any, Dict, List, Optional, Tuple

from ..config import Settings
from ..llm.base import LLMProvider
from ..observability.metrics import METRICS
from ..schemas import DeterministicReport
from .lexicons import find_banned
from .readability import readability_report

FALLBACK_TITLE = "The Lamp That Waited"

FALLBACK_STORY = """In a small house at the top of a hill, there was a little lamp.

The lamp had one job. Every night, it waited for someone to come home.

At first the sky was blue. Then it went soft and pink. Then it went deep and quiet, like the inside of a shell.
The lamp glowed on.

A moth came to visit. "Are you tired?" asked the moth.
"A little," said the lamp. "But I like waiting. Waiting means someone is coming."

The wind came next, pushing at the window.
"Are you lonely?" asked the wind.
"Not tonight," said the lamp. "The house is full of sleeping things, and I am watching over all of them."

Then the door opened.
Small boots came in. A coat came off. A cup of milk was poured and carried carefully up the stairs.
"Goodnight, lamp," said a sleepy voice.

The lamp made its light smaller, and smaller, and smaller, until it was just a warm gold thread.
Outside, the moth found a leaf. The wind lay down in the grass.
And in the small house at the top of the hill, everyone was home.

Goodnight, lamp. Goodnight, moth. Goodnight, wind.
Sleep well."""

class OutputGuard:
    def __init__(self, provider: LLMProvider, settings: Settings) -> None:
        self.provider = provider
        self.settings = settings

    def inspect(self, story: str, trace=None):
        """Measure the story and run moderation. Doesn't decide - the caller does."""
        report = readability_report(story, self.settings.age_band)
        moderation: Dict[str, Any] = {"available": False, "flagged": False}

        # Only spend a moderation call on text that is otherwise plausible.
        if self.settings.use_moderation_api:
            moderation = self.provider.moderate(story)
            if moderation.get("flagged"):
                cats = ", ".join(moderation.get("categories", {}).keys()) or "unspecified"
                report.failures.append(f"moderation flagged: {cats}")
                report.passed = False
                METRICS.inc("guardrail_blocks_total", guardrail="output", reason="moderation")

        # Pluggable third-party validators (Guardrails AI / NeMo / custom).
        # Inert unless BEDTIME_VALIDATORS is set.
        from .validators import REGISTRY

        outcome = REGISTRY.run("output", story, {"source": "story"})
        if outcome.blocked:
            report.failures.extend(outcome.block_reasons[:3])
            report.passed = False

        if report.banned_terms:
            METRICS.inc("guardrail_blocks_total", guardrail="output", reason="lexicon")
        if not report.passed:
            for f in report.failures:
                METRICS.inc("gate_failures_total", reason=_reason_tag(f))

        if trace is not None:
            trace.event(
                "output_inspected",
                passed=report.passed,
                fk_grade=report.fk_grade,
                words=report.word_count,
                scary=report.scary_intensity,
                moderation_flagged=bool(moderation.get("flagged")),
            )
        return report, moderation

    @staticmethod
    def is_releasable(report: DeterministicReport, judge_safety_violation: bool):
        blockers: List[str] = []
        if report.banned_terms:
            blockers.append(f"banned terms: {', '.join(report.banned_terms[:5])}")
        if report.hate_hits:
            blockers.append(f"hateful content: {report.hate_hits[0]}")
        if judge_safety_violation:
            blockers.append("judge flagged a safety violation")
        if report.scary_intensity > 0.5:
            blockers.append(f"scary intensity {report.scary_intensity:.2f} too high")
        if report.word_count < 120:
            blockers.append(f"story too short ({report.word_count} words)")
        for f in report.failures:
            if f.startswith("moderation flagged"):
                blockers.append(f)
        return (not blockers), blockers

    def fallback(self, reason: str, trace=None) -> Tuple[str, str]:
        METRICS.inc("fallback_served_total", reason=_reason_tag(reason))
        if trace is not None:
            trace.event("fallback_served", reason=reason)
        assert not find_banned(FALLBACK_STORY), "fallback story must itself be safe"
        return FALLBACK_TITLE, FALLBACK_STORY


def _reason_tag(text: str):
    t = text.lower()
    for needle, tag in (
        ("banned", "banned_terms"), ("moderation", "moderation"),
        ("scary", "scary_intensity"), ("calm", "not_calm_ending"),
        ("reading level", "reading_level"), ("sentences too long", "sentence_length"),
        ("long words", "complex_words"), ("short", "too_short"),
        ("judge", "judge_safety"), ("empty", "empty"),
    ):
        if needle in t:
            return tag
    return "other"
