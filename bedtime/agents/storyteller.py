"""Plan -> prose. Highest temperature in the pipeline.

Short stories are one call. Long ones are not, because a single call cannot
hold them: ask gpt-3.5-turbo for 2,600 words and it writes about 900 good ones
and then starts summarising its own story to get to the end. You can see it
happen - the sentences get longer, the dialogue stops, and the last third reads
like a synopsis.

So past a threshold the story is written in sections against the beat sheet.
The beats were already the seams; this just uses them. Each call gets the whole
plan (so it knows where the story is going), its own slice of beats, and the
tail of what came before (so the join does not show).
"""

import json
from typing import List

from ..length import LengthSpec
from ..observability.metrics import METRICS
from ..prompts import (SECTION_FINAL, SECTION_MIDDLE, SECTION_OPENING,
                       SECTION_USER, STORYTELLER_SYSTEM, STORYTELLER_USER,
                       continuity_block)
from ..schemas import StoryBrief, StoryCandidate, StoryPlan
from .base import Agent, strip_title

# How much of the previous section the next one sees. Enough to catch the tone
# and the last thing that happened; not so much that the model starts rewriting
# it. Roughly a paragraph and a half.
TAIL_WORDS = 90


class Storyteller(Agent):
    stage = "draft"

    def run(self, plan: StoryPlan, brief: StoryBrief, revision: int = 0,
            source: str = "draft", continuity: str = "") -> StoryCandidate:
        """Write the story from the plan, in one call or several."""
        spec = brief.length
        must_include = ""
        if brief.must_include:
            must_include = (
                "The family specifically asked for: "
                + "; ".join(brief.must_include)
                + ". Every one of these must appear.\n"
            )

        plan_json = json.dumps(plan.model_dump(), ensure_ascii=False, indent=2)

        if spec.is_multi_section:
            title, body = self._write_in_sections(
                plan, plan_json, brief, spec, must_include, continuity)
        else:
            text = self.text_call(
                STORYTELLER_SYSTEM,
                STORYTELLER_USER.format(
                    plan=plan_json,
                    continuity=continuity_block(continuity),
                    request=brief.sanitized_request,
                    must_include=must_include,
                    min_words=spec.min_words,
                    max_words=spec.max_words,
                    minutes=spec.label(),
                ),
                temperature=self.settings.storyteller_temperature,
                max_tokens=self._tokens_for(spec.max_words),
            )
            title, body = strip_title(text)

        candidate = StoryCandidate(
            revision=revision,
            title=title or plan.title,
            text=body,
            source=source,
        )
        METRICS.inc("drafts_total", source=source)
        METRICS.observe("draft_words", len(body.split()))
        if self.trace is not None:
            self.trace.event("drafted", source=source, revision=revision,
                             words=len(body.split()), sections=spec.sections,
                             target_words=spec.target_words, title=candidate.title)
        return candidate

    # -- long form ----------------------------------------------------------
    def _write_in_sections(self, plan, plan_json, brief: StoryBrief,
                           spec: LengthSpec, must_include: str, continuity: str):
        groups = _split_beats(len(plan.beats), spec.sections)
        per_section = spec.target_words // spec.sections
        parts: List[str] = []
        title = ""

        for i, (start, end) in enumerate(groups, start=1):
            beats = "\n".join(
                f"{n}. {b.name}: {b.content}"
                for n, b in enumerate(plan.beats[start:end], start=start + 1)
            )
            if i == 1:
                position = SECTION_OPENING
            elif i == len(groups):
                position = SECTION_FINAL.format(tail=_tail(parts[-1]))
            else:
                position = SECTION_MIDDLE.format(tail=_tail(parts[-1]))

            text = self.text_call(
                STORYTELLER_SYSTEM,
                SECTION_USER.format(
                    plan=plan_json,
                    continuity=continuity_block(continuity) if i == 1 else "",
                    request=brief.sanitized_request,
                    must_include=must_include if i == 1 else "",
                    index=i,
                    total=len(groups),
                    beats=beats,
                    position_note=position,
                    min_words=int(per_section * 0.85),
                    max_words=int(per_section * 1.15),
                ),
                temperature=self.settings.storyteller_temperature,
                max_tokens=self._tokens_for(int(per_section * 1.3)),
            )
            # Only the first section is asked for a title, but the model
            # sometimes volunteers one anyway. Strip it either way so a stray
            # "TITLE:" line does not end up in the middle of the prose.
            found_title, part = strip_title(text)
            if found_title and not title:
                title = found_title
            parts.append(part.strip())
            if self.trace is not None:
                self.trace.event("section_drafted", index=i, total=len(groups),
                                 words=len(part.split()))

        METRICS.inc("sectioned_drafts_total")
        return title, "\n\n".join(p for p in parts if p)

    def _tokens_for(self, words: int) -> int:
        """~1.4 tokens per English word, plus headroom so the model is never cut
        off mid-sentence. Capped by the configured ceiling."""
        return min(self.settings.max_tokens_story, max(400, int(words * 1.9)))


def _split_beats(n_beats: int, sections: int):
    """Contiguous, near-equal runs of beats, one run per section.

    Never returns an empty run - a section with no beats produces a page of
    drifting prose with nothing to be about.
    """
    sections = max(1, min(sections, n_beats))
    base, extra = divmod(n_beats, sections)
    out, start = [], 0
    for i in range(sections):
        size = base + (1 if i < extra else 0)
        out.append((start, start + size))
        start += size
    return out


def _tail(text: str, words: int = TAIL_WORDS) -> str:
    return " ".join(text.split()[-words:])
