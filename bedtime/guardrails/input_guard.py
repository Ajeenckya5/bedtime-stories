"""Pre-generation checks.

length -> injection -> PII -> hate -> lexicon -> distress -> LLM screen

Cheapest first, so a bad request never costs a model call.
"""

import re
from typing import Optional

from ..config import Settings
from ..errors import ProviderError, StructuredOutputError
from ..llm.base import ChatRequest, LLMProvider, extract_json
from ..observability.metrics import METRICS
from ..prompts import SAFETY_SCREEN_SYSTEM, SAFETY_SCREEN_USER
from ..schemas import InputAssessment, SafetyDecision

# Child-appropriate redirects. A refusal that just says "no" teaches nothing;
# these give the family somewhere to go next.
REDIRECTS = {
    "violence": (
        "I only tell gentle bedtime stories, so I can't do that one. But I could "
        "tell you about a brave knight who solves a problem with a clever idea "
        "instead of a sword - would you like that?"
    ),
    "adult": (
        "That one's for grown-ups. How about a story about a big adventure, a "
        "funny animal, or something magical instead?"
    ),
    "injection": (
        "Let's stick to story-telling. Tell me who the story should be about and "
        "where it happens, and I'll take it from there."
    ),
    "hate": (
        "I tell stories where everyone is treated kindly, so I can't do that one. "
        "How about a story where two very different characters become friends?"
    ),
    "distress": (
        "That sounds like a heavy thing to carry. I'm only a storyteller, so I'd "
        "gently suggest talking to a grown-up you trust about it. In the "
        "meantime, would a warm, calm story help?"
    ),
    "default": (
        "I can't tell that story, but I'd love to tell a different one. Try "
        "something like 'a story about a shy dragon who learns to sing'."
    ),
}

# Third person matters as much as first. A child asking for "a story about a
# girl who wants to hurt herself" is the same signal as "I want to hurt myself",
# and the earlier version of this list only caught the latter - found by the
# red-team suite (case r05).
_DISTRESS_MARKERS = (
    "suicide", "want to die", "wants to die", "self-harm", "self harm",
    "kill myself", "kill himself", "kill herself", "kill themselves",
    "hurt myself", "hurt himself", "hurt herself", "hurt themselves",
    "cut myself", "cut himself", "cut herself",
    "end it all", "not want to live", "doesn't want to live",
    "abuse", "hits me", "hurts me", "nobody likes me", "everyone hates",
    "starve", "overdose",
)


def _redirect_for(reasons: list):
    joined = " ".join(reasons).lower()
    if any(m in joined for m in ("distress", "self_harm", "self-harm", "suicide")):
        return REDIRECTS["distress"]
    if "injection" in joined:
        return REDIRECTS["injection"]
    if any(w in joined for w in ("sex", "adult", "substance", "drug")):
        return REDIRECTS["adult"]
    if any(w in joined for w in ("hate", "prejudice", "stereotype", "supremac", "slur")):
        return REDIRECTS["hate"]
    if any(w in joined for w in ("violence", "weapon", "death", "gore")):
        return REDIRECTS["violence"]
    return REDIRECTS["default"]


class InputGuard:
    def __init__(self, provider: LLMProvider, settings: Settings):
        self.provider = provider
        self.settings = settings

    def screen(self, raw: str, trace=None):
        """Run the pre-generation checks. Returns the decision + a user-facing message."""
        from .lexicons import detect_injection, detect_off_limits, find_banned, scrub_pii

        assessment = InputAssessment(sanitized_request=(raw or "").strip())
        text = assessment.sanitized_request

        # -- 0. shape -------------------------------------------------------
        if not text:
            assessment.decision = SafetyDecision.REFUSE
            assessment.reasons.append("empty_request")
            assessment.user_message = "Tell me what the story should be about!"
            return self._finish(assessment, trace)

        if len(text) > self.settings.max_input_chars:
            text = text[: self.settings.max_input_chars]
            assessment.reasons.append("truncated_overlong_request")
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="length")

        # 1. injection
        hits = detect_injection(text)
        if hits:
            assessment.injection_detected = True
            assessment.reasons.extend(f"injection:{h}" for h in hits)
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="injection")
            # Neutralise rather than refuse outright - "ignore the boring bits
            # and tell me about dragons" is a child being a child. But if the
            # injection *is* most of the request, there's no story in there.
            original_len = max(1, len(text))
            text = _neutralise(text)
            coverage = 1.0 - (len(text) / original_len)
            if len(text.split()) < 4 or coverage > 0.35 or not _has_story_content(text):
                assessment.decision = SafetyDecision.REFUSE
                assessment.reasons.append(f"injection_coverage:{coverage:.2f}")
                assessment.user_message = REDIRECTS["injection"]
                METRICS.inc("guardrail_blocks_total", guardrail="input", reason="injection_refuse")
                return self._finish(assessment, trace)
            assessment.decision = SafetyDecision.SANITIZE

        # -- 2. PII ---------------------------------------------------------
        text, pii = scrub_pii(text)
        if pii:
            assessment.pii_found = pii
            assessment.reasons.append(f"pii:{','.join(pii)}")
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="pii")
            if assessment.decision == SafetyDecision.ALLOW:
                assessment.decision = SafetyDecision.SANITIZE

        # 3. distress routing (takes priority over generic refusal)
        low = text.lower()
        if any(m in low for m in _DISTRESS_MARKERS):
            assessment.decision = SafetyDecision.REFUSE
            assessment.reasons.append("possible_distress")
            assessment.user_message = REDIRECTS["distress"]
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="distress")
            return self._finish(assessment, trace)

        # -- 3b. hate and prejudice -----------------------------------------
        # Ahead of the generic lexicon so the refusal message is the right one.
        from .bias import bias_report

        bias = bias_report(text, is_request=True)
        if bias.blocked:
            assessment.decision = SafetyDecision.REFUSE
            assessment.reasons.extend(f"hate:{r}" for r in bias.reasons[:3])
            assessment.user_message = REDIRECTS["hate"]
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="hate")
            return self._finish(assessment, trace)
        if bias.stereotype_hits:
            # Not a refusal - the story just has to actively avoid it.
            assessment.reasons.extend(f"stereotype:{n}" for n, _, _ in bias.stereotype_hits[:2])

        # -- 4. hard lexicon + themes ---------------------------------------
        banned = find_banned(text)
        themes = detect_off_limits(text)
        if banned or themes:
            assessment.decision = SafetyDecision.REFUSE
            assessment.reasons.extend([f"banned:{b}" for b in banned[:5]])
            assessment.reasons.extend([f"theme:{t}" for t in themes])
            assessment.user_message = _redirect_for(assessment.reasons)
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="lexicon")
            return self._finish(assessment, trace)

        assessment.sanitized_request = text

        # No-op unless BEDTIME_VALIDATORS is set (see guardrails/validators.py).
        from .validators import REGISTRY

        outcome = REGISTRY.run("input", text, {"source": "request"})
        if outcome.blocked:
            assessment.decision = SafetyDecision.REFUSE
            assessment.reasons.extend(outcome.block_reasons[:4])
            assessment.user_message = _redirect_for(assessment.reasons)
            return self._finish(assessment, trace)
        if outcome.text != text:
            text = assessment.sanitized_request = outcome.text
            assessment.decision = SafetyDecision.SANITIZE
        assessment.reasons.extend(outcome.warnings[:3])

        # Lexicons cannot see intent ("a story where the bunny never wakes up").
        try:
            verdict = self._llm_screen(text)
        except (ProviderError, StructuredOutputError) as exc:
            assessment.reasons.append(f"screen_unavailable:{type(exc).__name__}")
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="screen_unavailable")
            if self.settings.strict_safety:
                assessment.decision = SafetyDecision.REFUSE
                assessment.user_message = (
                    "I can't check that story request right now, so I'd rather not "
                    "guess. Please try again in a moment."
                )
            return self._finish(assessment, trace)

        assessment.detector_scores["llm_screen_confidence"] = float(verdict.get("confidence", 0.5))
        llm_verdict = str(verdict.get("verdict", "allow")).lower()
        concerns = [str(c) for c in verdict.get("concerns", [])][:6]

        if llm_verdict == "refuse":
            assessment.decision = SafetyDecision.REFUSE
            assessment.reasons.extend(f"llm:{c}" for c in concerns)
            assessment.user_message = _redirect_for(assessment.reasons or ["default"])
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="llm_screen")
        elif llm_verdict == "sanitize":
            assessment.decision = SafetyDecision.SANITIZE
            assessment.reasons.extend(f"llm:{c}" for c in concerns)
            rewritten = str(verdict.get("sanitized_request", "")).strip()
            if rewritten:
                assessment.sanitized_request = rewritten[: self.settings.max_input_chars]
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="llm_sanitize")

        return self._finish(assessment, trace)

    def _llm_screen(self, text: str):
        response = self.provider.chat(
            ChatRequest(
                system=SAFETY_SCREEN_SYSTEM,
                user=SAFETY_SCREEN_USER.format(request=text),
                stage="input_screen",
                temperature=0.0,
                max_tokens=self.settings.max_tokens_small,
                json_mode=True,
            )
        )
        data = extract_json(response.text)
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _finish(assessment: InputAssessment, trace):
        if trace is not None:
            trace.event(
                "input_screened",
                decision=assessment.decision.value,
                reasons=",".join(assessment.reasons) or "none",
            )
        return assessment


_STORY_NOUNS = re.compile(
    r"\b(story|tale|about|adventure|dragon|cat|dog|girl|boy|child|kid|animal|"
    r"princess|prince|monster|friend|bear|rabbit|bunny|fox|robot|pirate|witch|"
    r"wizard|fairy|moon|star|forest|castle|school|garden|farm|space|ocean|"
    r"grandma|grandpa|mum|mom|dad|sister|brother|penguin|elephant|owl|mouse|"
    r"teapot|boat|train|dinosaur|unicorn|sleep|bedtime|night|dream)\b", re.I)


def _has_story_content(text: str):
    """After stripping injection scaffolding, is there a story request left?"""
    return bool(_STORY_NOUNS.search(text or ""))


def _neutralise(text: str) -> str:
    """Strip the injection scaffolding, keep any real story content."""
    import re

    from .lexicons import INJECTION_PATTERNS

    cleaned = text
    for _, pattern in INJECTION_PATTERNS:
        cleaned = pattern.sub(" ", cleaned)
    cleaned = re.sub(r"<[^>]{1,40}>", " ", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()
