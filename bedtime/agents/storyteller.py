"""Plan -> prose. Highest temperature in the pipeline."""

import json

from ..observability.metrics import METRICS
from ..prompts import STORYTELLER_SYSTEM, STORYTELLER_USER, continuity_block
from ..schemas import StoryBrief, StoryCandidate, StoryPlan
from .base import Agent, strip_title


class Storyteller(Agent):
    stage = "draft"

    def run(self, plan: StoryPlan, brief: StoryBrief, revision: int = 0,
            source: str = "draft", continuity: str = "") -> StoryCandidate:
        """Write the story from the plan."""
        must_include = ""
        if brief.must_include:
            must_include = (
                "The family specifically asked for: "
                + "; ".join(brief.must_include)
                + ". Every one of these must appear.\n"
            )

        text = self.text_call(
            STORYTELLER_SYSTEM,
            STORYTELLER_USER.format(
                plan=json.dumps(plan.model_dump(), ensure_ascii=False, indent=2),
                continuity=continuity_block(continuity),
                request=brief.sanitized_request,
                must_include=must_include,
                min_words=self.settings.target_words_min,
                max_words=self.settings.target_words_max,
            ),
            temperature=self.settings.storyteller_temperature,
            max_tokens=self.settings.max_tokens_story,
        )

        title, body = strip_title(text)
        candidate = StoryCandidate(
            revision=revision,
            title=title or plan.title,
            text=body,
            source=source,
        )
        METRICS.inc("drafts_total", source=source)
        if self.trace is not None:
            self.trace.event("drafted", source=source, revision=revision,
                             words=len(body.split()), title=candidate.title)
        return candidate
