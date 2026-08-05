"""Targeted revision - specific fixes and quoted sentences, not "improve this"."""

from typing import List

from ..guardrails.readability import hardest_words, long_sentences
from ..length import length_note
from ..observability.metrics import METRICS
from ..prompts import REVISER_SYSTEM, REVISER_USER, numbered
from ..schemas import Assessment, StoryBrief, StoryCandidate
from .base import Agent, strip_title


class Reviser(Agent):
    stage = "revise"

    def run(self, candidate: StoryCandidate, assessment: Assessment,
            brief: StoryBrief, revision: int) -> StoryCandidate:
        """Apply the judge's fixes with as few other changes as possible."""
        fixes = self._build_fixes(assessment)
        extra = self._build_targets(candidate.text, assessment)

        # Length goes first in the list. It is the one fix that changes how much
        # room every other fix has to work in, and a story that is half the
        # requested length is the defect a family notices before any of the
        # subtler ones.
        note = length_note(brief.length, len(candidate.text.split()))
        if note:
            fixes.insert(0, note)
            METRICS.inc("length_corrections_total")

        text = self.text_call(
            REVISER_SYSTEM,
            REVISER_USER.format(
                story=f"TITLE: {candidate.title}\n\n{candidate.text}",
                fixes=numbered(fixes),
                extra_targets=extra,
                request=brief.sanitized_request,
                min_words=brief.length.min_words,
                max_words=brief.length.max_words,
            ),
            temperature=self.settings.reviser_temperature,
            max_tokens=min(self.settings.max_tokens_story,
                           max(600, int(brief.length.max_words * 1.9))),
        )

        title, body = strip_title(text)
        revised = StoryCandidate(
            revision=revision,
            title=title or candidate.title,
            text=body,
            source="revision",
        )
        METRICS.inc("revisions_total", revision=str(revision))
        if self.trace is not None:
            self.trace.event("revised", revision=revision, fixes=len(fixes),
                             words=len(body.split()))
        return revised

    @staticmethod
    def _build_fixes(assessment: Assessment):
        fixes: List[str] = list(assessment.must_fix)
        det = assessment.deterministic

        if det.banned_terms:
            fixes.insert(0, (
                "Remove these words completely and rewrite around them: "
                + ", ".join(det.banned_terms[:6])
            ))
        if not det.ends_calmly:
            fixes.append(
                "Rewrite the final paragraph so the story settles: short sentences, "
                "a warm safe image, and an explicit goodnight or falling-asleep beat. "
                "No cliffhanger, no excitement in the last three sentences."
            )
        if det.scary_intensity > 0.35:
            fixes.append(
                f"The story reads as too frightening (intensity {det.scary_intensity:.2f}). "
                "Soften every frightening image, and make sure any worry a character "
                "feels is explicitly comforted before the story ends."
            )
        if det.bias_fixes:
            # Ahead of style fixes: how people are portrayed matters more than
            # how the prose sounds.
            for fix in det.bias_fixes[:2]:
                fixes.insert(0, fix)
        if det.ai_tells:
            fixes.insert(0, (
                "This reads as machine-written. Fix these exactly: "
                + "; ".join(det.ai_tells[:4])
                + ". Replace stock phrases with something specific and slightly odd, "
                  "and vary sentence lengths much more (two-word sentences next to long ones)."
            ))
        # A flat "under 400 words is too short" check used to live here. It is
        # wrong now that length is per-request: 400 words is short for a ten
        # minute story and slightly long for a two minute one. length_note()
        # does this properly against what the family actually asked for.
        return fixes[:6] or ["Tighten the prose without changing the plot."]

    @staticmethod
    def _build_targets(text: str, assessment: Assessment):
        det = assessment.deterministic
        blocks: List[str] = []

        longs = long_sentences(text, threshold=22, limit=4)
        if longs:
            quoted = "\n".join(f'   - "{s[:160]}"' for s in longs)
            blocks.append(
                "SPLIT THESE SENTENCES into two or three short ones each "
                f"(target 8-14 words). Keep every detail:\n{quoted}"
            )

        hard = hardest_words(text, limit=10)
        if hard and det.complex_word_ratio > 0.07:
            blocks.append(
                "REPLACE THESE WORDS with simpler ones a 6-year-old would use: "
                + ", ".join(hard)
            )

        if det.ai_tells:
            stock = [t.split('"')[1] for t in det.ai_tells if t.startswith("stock phrase")][:6]
            if stock:
                blocks.append(
                    "DELETE THESE PHRASES and write something specific in their place: "
                    + ", ".join(f'"{s}"' for s in stock)
                )

        weak = sorted(assessment.dimension_medians.items(), key=lambda kv: kv[1])[:2]
        weak = [(d, s) for d, s in weak if s < 4.0]
        if weak:
            hints = {
                "narrative_arc": "make the want and the obstacle unmistakable in the first "
                                 "third, and let the resolution be earned by something the "
                                 "protagonist notices or does",
                "engagement": "add one specific, surprising, concrete image a child would "
                              "repeat the next morning",
                "language_fit": "shorten sentences and swap abstract words for physical ones",
                "bedtime_suitability": "slow the final paragraph right down and end on a warm, "
                                       "still image",
                "age_appropriateness": "soften anything frightening and comfort every worry",
                "prompt_adherence": "put the requested characters and premise at the centre",
                "human_voice": "cut every stock phrase, vary sentence length hard, and delete "
                               "any sentence that explains what the story means",
            }
            blocks.append(
                "WEAKEST DIMENSIONS: "
                + "; ".join(f"{d} ({s}/5) - {hints.get(d, 'strengthen this')}" for d, s in weak)
            )

        return ("\n" + "\n\n".join(blocks) + "\n") if blocks else "\n"
