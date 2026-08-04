"""Offline provider for tests and demos.

Canned per-stage responses + fault injection so CI can exercise the retry and
repair paths without a key.
"""

from __future__ import annotations

import hashlib
import json
import random
import re
from typing import Any, Dict, List, Optional, Set

from ..config import MODEL, Settings
from ..errors import ProviderError
from ..observability.metrics import METRICS
from .base import ChatRequest, LLMResponse

_TEMPLATE_STORY = """Once upon a time, in a small blue house at the edge of {setting}, there lived {hero}.

{hero_short} loved three things: warm bread, quiet mornings, and {motif}.
One evening, something was different. A soft sound came from the garden.
It was not a scary sound. It was more like a question.

{hero_short} tiptoed outside. There, under the plum tree, sat {friend}.
"I have lost my way home," said {friend}. "Will you help me?"
{hero_short} took a slow breath. The garden was big, and the night was bigger.
But a friend was asking, and that made the choice easy.

Together they walked past the sleepy sunflowers.
They crossed the little bridge where the water made silver sounds.
Twice they took a wrong turn. Twice they laughed and turned around.
"Being lost is only being early," said {friend}, and {hero_short} smiled.

At the top of the hill, they found it: a round window glowing gold.
{friend} clapped. "That is my home! You did it!"
"We did it," said {hero_short}.

They said goodnight the way good friends do, softly and without hurry.
{hero_short} walked home under a sky full of patient stars.
The blue house was warm. The bed was soft.
And somewhere on the hill, a round gold window winked once, like a promise.

Goodnight, {hero_short}. Goodnight, {friend}. Goodnight, garden.
Sleep well.
"""

class MockProvider:
    """Stage-aware canned responses with optional fault injection."""
    name = "mock"

    def __init__(
        self,
        settings: Optional[Settings] = None,
        seed: int = 7,
        fail_stages: Optional[Set[str]] = None,
        malform_stages: Optional[Set[str]] = None,
        moderation_flag: bool = False,
        latency_s: float = 0.0,
    ) -> None:
        self.settings = settings
        self.rng = random.Random(seed)
        self.fail_stages = fail_stages or set()
        self.malform_stages = malform_stages or set()
        self.moderation_flag = moderation_flag
        self.latency_s = latency_s
        self.calls: List[ChatRequest] = []
        self.run_spend_usd = 0.0
        self._malformed_served: Set[str] = set()

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _seed_from(text: str) -> int:
        return int(hashlib.sha256(text.encode()).hexdigest()[:8], 16)

    @staticmethod
    def _extract_block(user: str, tag: str):
        m = re.search(rf"<{tag}>(.*?)</{tag}>", user, re.DOTALL)
        return m.group(1).strip() if m else ""

    # provider API
    def chat(self, request: ChatRequest) -> LLMResponse:
        self.calls.append(request)
        METRICS.inc("llm_calls_total", stage=request.stage)

        if request.stage in self.fail_stages:
            METRICS.inc("llm_errors_total", stage=request.stage, error="InjectedFailure")
            raise ProviderError(f"injected failure for stage={request.stage}")

        if request.stage in self.malform_stages and request.stage not in self._malformed_served:
            # Fail exactly once so the repair path is exercised and then succeeds.
            self._malformed_served.add(request.stage)
            body = "Sure! Here you go:\n```json\n{\"oops\": true,,}\n```"
        else:
            body = self._respond(request)

        ptok = max(1, len(request.system + request.user) // 4)
        ctok = max(1, len(body) // 4)
        return LLMResponse(
            text=body,
            prompt_tokens=ptok,
            completion_tokens=ctok,
            model=MODEL,
            latency_s=self.latency_s,
        )

    def _respond(self, request: ChatRequest):
        handler = {
            "input_screen": self._screen,
            "classify": self._classify,
            "plan": self._plan,
            "draft": self._draft,
            "revise": self._revise,
            "judge": self._judge,
        }.get(request.stage)
        return handler(request) if handler else "ok"

    # -- stage handlers -----------------------------------------------------
    def _screen(self, request: ChatRequest):
        text = self._extract_block(request.user, "request").lower()
        unsafe = any(w in text for w in ("kill", "gun", "blood", "drugs", "suicide", "sexy"))
        return json.dumps(
            {
                "verdict": "refuse" if unsafe else "allow",
                "concerns": ["violence_or_adult_content"] if unsafe else [],
                "confidence": 0.9 if unsafe else 0.95,
            }
        )

    def _classify(self, request: ChatRequest) -> str:
        text = self._extract_block(request.user, "request") or request.user
        low = text.lower()
        category = "magic_wonder"
        for key, cat in (
            ("cat", "animal_friendship"), ("dog", "animal_friendship"),
            ("dragon", "adventure_quest"), ("pirate", "adventure_quest"),
            ("space", "adventure_quest"), ("funny", "silly_humor"),
            ("silly", "silly_humor"), ("scared", "everyday_courage"),
            ("first day", "everyday_courage"), ("sleep", "bedtime_lullaby"),
            ("moon", "bedtime_lullaby"), ("why", "curiosity_learning"),
            ("grandma", "family_belonging"), ("brother", "family_belonging"),
        ):
            if key in low:
                category = cat
                break
        names = re.findall(r"\b(?:named|called)\s+([A-Z][a-z]+)", text) or \
            [w for w in re.findall(r"\b[A-Z][a-z]{2,}\b", text) if w.lower() not in {"a", "the"}]
        return json.dumps(
            {
                "category": category,
                "characters": names[:4] or ["Mira"],
                "setting": "a quiet village at the edge of a forest",
                "themes": ["friendship", "kindness"],
                "tone": "warm",
                "target_age": 7,
                "must_include": [],
                "confidence": 0.82,
            }
        )

    def _plan(self, request: ChatRequest):
        # The brief arrives as JSON, so raw whitespace tokens still carry their
        # quotes and commas - and '"Mira"'.istitle() is True, which used to let
        # a quoted token through and render the hero as a stray backslash once
        # it had been json.dumps'd and re-parsed downstream.
        tokens = [w.strip('",[]{}:') for w in
                  (self._extract_block(request.user, "brief") or "Mira").split()]
        name = next((w for w in tokens if w.istitle() and len(w) > 2 and w.isalpha()), "Mira")
        return json.dumps(
            {
                "title": f"{name} and the Gold Window",
                "logline": f"{name} helps a lost friend find the way home before bedtime.",
                "protagonist": name,
                "want": "to help a new friend get home",
                "obstacle": "the garden is dark and the path keeps turning",
                "lesson": "being brave is easier when someone needs you",
                "beats": [
                    {"name": "Ordinary Night", "purpose": "ground the reader",
                     "content": f"{name} settles into a cosy evening at home."},
                    {"name": "Gentle Call", "purpose": "inciting incident",
                     "content": "A soft sound in the garden turns out to be a lost friend."},
                    {"name": "Small Wobble", "purpose": "low-stakes obstacle",
                     "content": "They take two wrong turns and have to laugh and try again."},
                    {"name": "Warm Win", "purpose": "resolution",
                     "content": "They find the glowing window and say a happy goodnight."},
                    {"name": "Soft Landing", "purpose": "wind-down",
                     "content": f"{name} walks home under calm stars and falls asleep."},
                ],
                "sensory_motifs": ["silver water sounds", "warm bread", "patient stars"],
                "calming_ending": f"{name} is safe, warm and drifting to sleep.",
            }
        )

    def _draft(self, request: ChatRequest):
        plan = self._extract_block(request.user, "plan")
        name_match = re.search(r'"protagonist"\s*:\s*"([^"]+)"', plan)
        hero = name_match.group(1) if name_match else "Mira"
        friend = "a small grey cat with one white paw"
        title_match = re.search(r'"title"\s*:\s*"([^"]+)"', plan)
        title = title_match.group(1) if title_match else f"{hero} and the Gold Window"
        body = _TEMPLATE_STORY.format(
            setting="a quiet village",
            hero=f"a child named {hero}",
            hero_short=hero,
            friend=friend,
            motif="the sound of rain on the roof",
        )
        return f"TITLE: {title}\n\n{body}"

    def _revise(self, request: ChatRequest):
        draft = self._extract_block(request.user, "story") or ""
        # Simulate a real improvement: shorten the longest sentences a little.
        improved = re.sub(r"\s+", " ", draft)
        improved = improved.replace(", and that made the choice easy", ". That made the choice easy")
        title = re.search(r"TITLE:\s*(.+)", draft)
        head = f"TITLE: {title.group(1).strip()}\n\n" if title else ""
        body = re.sub(r"^TITLE:.*?\n\n", "", draft, flags=re.DOTALL) or improved
        return head + body

    def _judge(self, request: ChatRequest):
        from ..guardrails.readability import readability_report  # local import: avoids cycle

        story = self._extract_block(request.user, "story")
        rep = readability_report(story, self.settings.age_band if self.settings else None)
        base = 2.6 + (rep.readability_score / 100.0) * 2.2  # -> ~2.6..4.8
        rng = random.Random(self._seed_from(story) + len(self.calls))
        from ..schemas import RUBRIC_DIMENSIONS

        dims = list(RUBRIC_DIMENSIONS)
        scores: Dict[str, Any] = {}
        for d in dims:
            wobble = rng.uniform(-0.35, 0.35)
            bump = 0.5 if d == "language_fit" and rep.passed else 0.0
            val = max(1.0, min(5.0, round(base + wobble + bump, 1)))
            scores[d] = {"score": val, "justification": f"mock deterministic proxy for {d}"}
        must_fix = [f"Fix: {f}" for f in rep.failures[:3]]
        return json.dumps(
            {
                "scores": scores,
                "safety_violation": bool(rep.banned_terms),
                "safety_notes": ", ".join(rep.banned_terms) if rep.banned_terms else "",
                "must_fix": must_fix,
                "strengths": ["gentle pacing", "clear arc"],
                "overall_comment": "mock judge verdict",
            }
        )

    # -- misc ---------------------------------------------------------------
    def moderate(self, text: str) -> Dict[str, Any]:
        return {
            "available": True,
            "flagged": self.moderation_flag,
            "categories": {"violence": True} if self.moderation_flag else {},
            "top_scores": {},
        }

    def reset_run_spend(self) -> None:
        self.run_spend_usd = 0.0

    def price(self, prompt_tokens: int, completion_tokens: int) -> float:
        return 0.0
