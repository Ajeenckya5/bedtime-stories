"""Beat-sheet planner. Plan-then-write is what gives the story an arc."""

import json
from typing import Optional

from ..errors import ProviderError, StructuredOutputError
from ..observability.metrics import METRICS
from ..prompts import (LONG_PLAN_GUIDANCE, PLANNER_SYSTEM, PLANNER_USER,
                       continuity_block, strategy_for)
from ..schemas import StoryBeat, StoryBrief, StoryPlan
from .base import Agent

_PLAN_SCHEMA_HINT = (
    '{"title": "...", "logline": "...", "protagonist": "...", "want": "...", '
    '"obstacle": "...", "lesson": "...", '
    '"beats": [{"name": "...", "purpose": "...", "content": "..."}], '
    '"sensory_motifs": ["...", "...", "..."], "calming_ending": "..."}'
)


class Planner(Agent):
    stage = "plan"

    def run(self, brief: StoryBrief, continuity: str = ""):
        """Build the beat sheet. Synthesises a skeleton plan if the model fails."""
        strategy = strategy_for(brief.category)
        brief_block = self._render_brief(brief)
        spec = brief.length

        try:
            plan, repaired = self.structured_call(
                PLANNER_SYSTEM,
                PLANNER_USER.format(
                    brief=brief_block,
                    continuity=continuity_block(continuity),
                    category=brief.category.value,
                    arc=strategy["arc"],
                    guidance=strategy["guidance"],
                    pacing=strategy["pacing"],
                    n_beats=spec.beats,
                    target_words=spec.target_words,
                    minutes=spec.label(),
                    words_per_beat=spec.target_words // spec.beats,
                    length_guidance=LONG_PLAN_GUIDANCE if spec.beats >= 8 else "",
                ),
                StoryPlan,
                temperature=self.settings.planner_temperature,
                max_tokens=self.settings.max_tokens_plan,
                schema_hint=_PLAN_SCHEMA_HINT,
            )
            if repaired:
                METRICS.inc("plan_repaired_total")
        except (ProviderError, StructuredOutputError) as exc:
            # A missing plan would sink the whole run, so synthesise a valid
            # one from the brief and let the storyteller carry it.
            METRICS.inc("plan_fallback_total", error=type(exc).__name__)
            if self.trace is not None:
                self.trace.event("plan_fallback", error=str(exc)[:160])
            plan = self._skeleton_plan(brief)

        plan = self._enforce(plan, brief)
        if self.trace is not None:
            self.trace.event("planned", title=plan.title, beats=len(plan.beats),
                             obstacle=plan.obstacle[:80])
        return plan

    # -- helpers ------------------------------------------------------------
    @staticmethod
    def _render_brief(brief: StoryBrief):
        return json.dumps(
            {
                "request": brief.sanitized_request,
                "characters": brief.characters,
                "setting": brief.setting,
                "themes": brief.themes,
                "tone": brief.tone,
                "target_age": brief.target_age,
                "must_include": brief.must_include,
            },
            ensure_ascii=False,
            indent=2,
        )

    def _enforce(self, plan: StoryPlan, brief: StoryBrief) -> StoryPlan:
        # The model is asked for a specific beat count and usually gives it,
        # but it drifts on the long ones - ask for twelve and you often get
        # eight. Top up rather than re-plan: a short plan still works, it just
        # gives the storyteller less to write against, and each missing beat is
        # roughly 200 words the story will come out short.
        wanted = brief.length.beats
        while len(plan.beats) < wanted:
            plan.beats.append(
                StoryBeat(
                    name="Soft Landing" if len(plan.beats) == wanted - 1 else "A Quiet Turn",
                    purpose="wind the reader down toward sleep"
                    if len(plan.beats) == wanted - 1 else "let the story breathe",
                    content=plan.calming_ending
                    or f"{plan.protagonist} settles somewhere warm and safe as the night goes quiet.",
                )
            )
        del plan.beats[wanted:]
        if not plan.calming_ending:
            plan.calming_ending = (
                f"{plan.protagonist} is warm, safe, and drifting off to sleep."
            )
        if len(plan.sensory_motifs) < 2:
            plan.sensory_motifs = (plan.sensory_motifs +
                                   ["the smell of warm bread", "a soft yellow light",
                                    "the hush of wind in leaves"])[:3]
        # Keep the family's own words in the title where we can.
        if brief.characters and not any(
            c.split()[0].lower() in plan.title.lower() for c in brief.characters
        ):
            first = brief.characters[0].split()[0]
            plan.title = f"{first} and {plan.title}" if len(plan.title.split()) <= 5 else plan.title
        return plan

    def _skeleton_plan(self, brief: StoryBrief):
        hero = (brief.characters[0].split()[0] if brief.characters else "Nia")
        strategy = strategy_for(brief.category)
        stations = [s.strip() for s in strategy["arc"].split("->")]
        wanted = brief.length.beats
        beats = [
            StoryBeat(name=name.title(), purpose=f"beat {i + 1} of the {brief.category.value} arc",
                      content=f"{hero} moves through: {name}.")
            for i, name in enumerate(stations[:wanted])
        ]
        while len(beats) < wanted:
            beats.append(StoryBeat(name="Soft Landing", purpose="wind down",
                                   content=f"{hero} settles in somewhere warm and safe."))
        return StoryPlan(
            title=f"{hero} and the Quiet Light",
            logline=f"{hero} helps someone and finds their way back to a warm bed.",
            protagonist=f"{hero}, curious and kind",
            want="to help a friend",
            obstacle="the way is confusing and the night is getting late",
            lesson="asking for help is its own kind of brave",
            beats=beats,
            sensory_motifs=["a soft yellow light", "the smell of warm bread",
                            "the hush of wind in leaves"],
            calming_ending=f"{hero} is warm, safe, and drifting off to sleep.",
        )
