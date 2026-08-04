"""Request -> StoryBrief + category routing. Falls back to keywords on error."""

from __future__ import annotations

import re
from typing import List, Optional

from pydantic import BaseModel, Field

from ..errors import ProviderError, StructuredOutputError
from ..observability.metrics import METRICS
from ..prompts import CLASSIFY_SYSTEM, CLASSIFY_USER
from ..schemas import StoryBrief, StoryCategory
from .base import Agent

# Keyword fallback, ordered by specificity. Only used when the model call fails.
_HEURISTIC: List[tuple] = [
    (StoryCategory.BEDTIME_LULLABY, ("sleep", "sleepy", "bedtime", "lullaby", "dream",
                                     "moon", "stars", "night night", "calm")),
    (StoryCategory.EVERYDAY_COURAGE, ("scared", "afraid", "shy", "nervous", "first day",
                                      "brave", "worried", "school", "doctor", "dentist")),
    (StoryCategory.SILLY_HUMOR, ("funny", "silly", "giggle", "laugh", "ridiculous",
                                 "joke", "wacky", "goofy")),
    (StoryCategory.CURIOSITY_LEARNING, ("why", "how does", "how do", "learn", "discover",
                                        "science", "explain", "curious")),
    (StoryCategory.FAMILY_BELONGING, ("mum", "mom", "dad", "grandma", "grandpa", "granny",
                                      "sister", "brother", "family", "cousin", "baby")),
    (StoryCategory.ADVENTURE_QUEST, ("adventure", "quest", "journey", "pirate", "space",
                                     "treasure", "explore", "dragon", "castle", "knight",
                                     "map", "island", "rocket")),
    (StoryCategory.ANIMAL_FRIENDSHIP, ("cat", "dog", "puppy", "kitten", "rabbit", "bunny",
                                       "bear", "fox", "horse", "pet", "mouse", "duck",
                                       "elephant", "penguin", "owl", "friend")),
    (StoryCategory.MAGIC_WONDER, ("magic", "magical", "fairy", "wizard", "witch", "spell",
                                  "enchanted", "unicorn", "wish", "talking")),
]

_STOPWORD_NAMES = {
    "A", "An", "The", "I", "My", "Please", "Tell", "Story", "Once", "Can", "Could",
    "Would", "About", "And", "But", "Her", "His", "Their", "It", "We", "You",
}


class _RawBrief(BaseModel):
    """Loose shape of the classifier's JSON. Kept separate from StoryBrief so a
    sloppy model response is coerced in one place instead of everywhere."""
    category: str = "magic_wonder"
    characters: List[str] = Field(default_factory=list)
    setting: str = ""
    themes: List[str] = Field(default_factory=list)
    tone: str = "warm"
    target_age: int = 7
    must_include: List[str] = Field(default_factory=list)
    confidence: float = 0.5


class Classifier(Agent):
    stage = "classify"

    def run(self, sanitized_request: str, raw_request: Optional[str] = None) -> StoryBrief:
        """Turn free text into a StoryBrief. Falls back to keywords on error."""
        raw_request = raw_request if raw_request is not None else sanitized_request
        try:
            parsed, repaired = self.structured_call(
                CLASSIFY_SYSTEM,
                CLASSIFY_USER.format(request=sanitized_request),
                _RawBrief,
                temperature=self.settings.classifier_temperature,
                max_tokens=self.settings.max_tokens_small,
                schema_hint='{"category": "...", "characters": [...], "setting": "...", '
                            '"themes": [...], "tone": "...", "target_age": 7, '
                            '"must_include": [...], "confidence": 0.0-1.0}',
            )
            brief = self._to_brief(parsed, sanitized_request, raw_request)
            if repaired:
                METRICS.inc("classify_repaired_total")
        except (ProviderError, StructuredOutputError) as exc:
            METRICS.inc("classify_fallback_total", error=type(exc).__name__)
            if self.trace is not None:
                self.trace.event("classify_fallback", error=str(exc)[:160])
            brief = self._heuristic_brief(sanitized_request, raw_request)

        METRICS.inc("requests_by_category_total", category=brief.category.value)
        if self.trace is not None:
            self.trace.event(
                "classified",
                category=brief.category.value,
                confidence=round(brief.classification_confidence, 2),
                characters=", ".join(brief.characters[:4]) or "none",
            )
        return brief

    # -- coercion -----------------------------------------------------------
    def _to_brief(self, parsed: _RawBrief, sanitized: str, raw: str) -> StoryBrief:
        try:
            category = StoryCategory(parsed.category.strip().lower())
        except ValueError:
            category = self._heuristic_category(sanitized)
            parsed.confidence = min(parsed.confidence, 0.4)

        characters = [c.strip() for c in parsed.characters if c and c.strip()][:5]
        # Never lose a name the family gave us, even if the model dropped it.
        for name in self._names_in(raw):
            if not any(name.lower() in c.lower() for c in characters):
                characters.append(name)

        must_include = [m.strip() for m in parsed.must_include if m and m.strip()][:6]
        return StoryBrief(
            raw_request=raw,
            sanitized_request=sanitized,
            category=category,
            characters=characters[:6],
            setting=parsed.setting.strip() or "a small, warm place near home",
            themes=[t.strip() for t in parsed.themes if t and t.strip()][:5] or ["kindness"],
            tone=parsed.tone.strip().lower() or "warm",
            target_age=parsed.target_age,
            must_include=must_include,
            classification_confidence=max(0.0, min(1.0, parsed.confidence)),
        )

    def _heuristic_brief(self, sanitized: str, raw: str):
        return StoryBrief(
            raw_request=raw,
            sanitized_request=sanitized,
            category=self._heuristic_category(sanitized),
            characters=self._names_in(raw)[:4],
            setting="a small, warm place near home",
            themes=["kindness", "friendship"],
            tone="warm",
            target_age=7,
            must_include=[],
            classification_confidence=0.25,
        )

    @staticmethod
    def _heuristic_category(text: str):
        low = text.lower()
        for category, keywords in _HEURISTIC:
            if any(k in low for k in keywords):
                return category
        return StoryCategory.MAGIC_WONDER

    # TODO: capitalised-word heuristic picks up sentence-initial words sometimes.
    # A proper NER pass would be better but that's another dependency.
    @staticmethod
    def _names_in(text: str):
        explicit = re.findall(r"\b(?:named|called)\s+([A-Z][a-z]{1,15})", text)
        capitals = re.findall(r"\b([A-Z][a-z]{2,15})\b", text)
        out: List[str] = []
        for name in explicit + capitals:
            if name in _STOPWORD_NAMES or name in out:
                continue
            out.append(name)
        return out
