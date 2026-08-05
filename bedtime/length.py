"""How long is a story, and how do you ask for one.

The system used to have a single fixed target of 550-900 words for everything.
If you asked for "a five minute story" the words "five minute" went nowhere -
the classifier dropped them and you got the same ~600 words as always, which is
about four and a half minutes read aloud. Asking for twenty minutes got you the
same thing.

Two numbers matter here.

READ_ALOUD_WPM is 130, not the 200-250 you would use for silent adult reading.
Reading to a five-year-old is slower: you do voices, you pause on the pictures,
you stop when they ask what a heron is. 130 is the middle of the range usually
quoted for read-aloud pacing and it matches the narration speed we set for TTS
(0.92 of normal), so the printed estimate and the audio length agree.

WORDS_PER_SECTION is 700. That is not a model limit, it is a quality limit. Ask
gpt-3.5-turbo for 2,500 words in one call and it does not refuse - it writes
about 900 good ones and then starts summarising its own story to reach the end.
Long stories are therefore written in sections against the beat sheet, which is
what the beat sheet was always for.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Optional

READ_ALOUD_WPM = 130

MIN_MINUTES = 2.0
MAX_MINUTES = 20.0
DEFAULT_MINUTES = 5.0

# One call's worth of prose that stays good all the way through.
WORDS_PER_SECTION = 700

# The band is +/-15%. Tighter than that and a perfectly good story fails for
# being 40 words short, which is a worse outcome than a story that runs a
# little long.
TOLERANCE = 0.15


@dataclass(frozen=True)
class LengthSpec:
    """Everything downstream needs in order to hit a requested length."""
    minutes: float
    target_words: int
    min_words: int
    max_words: int
    beats: int
    sections: int

    @property
    def is_multi_section(self) -> bool:
        return self.sections > 1

    def label(self) -> str:
        m = self.minutes
        return f"{m:.0f} min" if abs(m - round(m)) < 0.05 else f"{m:.1f} min"


def clamp_minutes(minutes: float) -> float:
    return max(MIN_MINUTES, min(MAX_MINUTES, float(minutes)))


def words_for(minutes: float) -> int:
    return int(round(clamp_minutes(minutes) * READ_ALOUD_WPM))


def minutes_for(words: int) -> float:
    return round(max(0, words) / READ_ALOUD_WPM, 1)


def _beats_for(target_words: int) -> int:
    """Beats scale with length, but not linearly.

    A 2-minute story still needs a beginning, a middle and an end - you cannot
    have fewer than three and still have a shape. A 20-minute story does not
    need thirty beats; it needs about a dozen, each given more room. Past that
    the plan stops being a spine and becomes a summary of the story, and the
    storyteller starts transcribing it instead of writing.
    """
    return max(3, min(12, 3 + round(target_words / 220)))


def spec_for(minutes: Optional[float]) -> LengthSpec:
    minutes = clamp_minutes(DEFAULT_MINUTES if minutes is None else minutes)
    target = words_for(minutes)
    return LengthSpec(
        minutes=minutes,
        target_words=target,
        min_words=int(round(target * (1 - TOLERANCE))),
        max_words=int(round(target * (1 + TOLERANCE))),
        beats=_beats_for(target),
        sections=max(1, math.ceil(target / WORDS_PER_SECTION)),
    )


# --- parsing what the family actually typed --------------------------------

_NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "half": 0.5, "a couple of": 2, "a few": 3,
}

# "5 minute", "5-minute", "5 mins", "about ten minutes", "20 min long"
_EXPLICIT = re.compile(
    r"\b(?:(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?|(" + "|".join(_NUMBER_WORDS) + r"))\s*"
    r"[-–]?\s*(?:minute|minutes|min|mins)\b",
    re.I,
)

# Vague asks. Mapped to the middle of what people seem to mean by them.
_VAGUE = [
    (re.compile(r"\b(?:really|very|extra)\s+long\b|\bepic\b|\bbig\s+long\b", re.I), 15.0),
    (re.compile(r"\bnovel[- ]?length\b|\bchapter\s+story\b|\blong\s+chapter\b", re.I), 15.0),
    (re.compile(r"\blong(?:er)?\s+(?:story|one|bedtime)\b|\ba\s+long\s+", re.I), 10.0),
    (re.compile(r"\b(?:really|very|super)\s+(?:short|quick|fast)\b", re.I), 2.0),
    (re.compile(r"\bshort(?:er)?\s+(?:story|one)\b|\bquick\s+(?:story|one)\b"
                r"|\bjust\s+a\s+(?:short|quick|little)\b|\bin\s+a\s+hurry\b", re.I), 3.0),
]


def parse_minutes(text: str) -> Optional[float]:
    """Pull a requested reading length out of a free-text request.

    Deterministic on purpose. This is a regex rather than a field on the
    classifier's JSON because a number the family typed should not survive a
    round trip through a language model that is bad at arithmetic and will
    occasionally decide five means "medium". It also means the length is known
    before any model call, so it can be shown in the UI immediately and it
    costs nothing when the request has no length in it at all.
    """
    if not text:
        return None

    m = _EXPLICIT.search(text)
    if m:
        lo, hi, word = m.group(1), m.group(2), m.group(3)
        if word:
            return clamp_minutes(_NUMBER_WORDS[word.lower()])
        if hi:                                   # "10-15 minutes" -> take the middle
            return clamp_minutes((int(lo) + int(hi)) / 2)
        return clamp_minutes(int(lo))

    for pattern, minutes in _VAGUE:
        if pattern.search(text):
            return minutes
    return None


def length_note(spec: LengthSpec, actual_words: int) -> Optional[str]:
    """A specific instruction for the reviser, or None if the length is fine.

    Names the gap in both words and minutes. "Make it longer" gets a paragraph
    of padding; "you are 380 words short, which is three minutes" gets scenes.
    """
    if spec.min_words <= actual_words <= spec.max_words:
        return None
    if actual_words < spec.min_words:
        short_by = spec.target_words - actual_words
        return (
            f"This runs {actual_words} words, about {minutes_for(actual_words):.1f} "
            f"minutes read aloud. The family asked for {spec.label()}, which is "
            f"about {spec.target_words} words - it is {short_by} words short. "
            "Do not pad it with description or repeat what already happened. "
            "Find the two or three beats that are being rushed and give them "
            "room: what the character does next, what someone says back, what "
            "goes wrong before it goes right."
        )
    over_by = actual_words - spec.target_words
    return (
        f"This runs {actual_words} words, about {minutes_for(actual_words):.1f} "
        f"minutes. The family asked for {spec.label()}. Cut roughly {over_by} "
        "words. Take them out of the middle, not the ending - the wind-down "
        "must stay."
    )
