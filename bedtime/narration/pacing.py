"""Prepare story text for read-aloud delivery.

First version of this littered the text with ellipses at every paragraph break.
That was wrong, and obviously wrong once you listened to it: paragraphs in this
prose style are often a single line, so the result stopped dead after every
"""

import re
from dataclasses import dataclass, field
from typing import List

_PARA = re.compile(r"\n\s*\n")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")

# A beat. One is plenty - the earlier version used three lengths and they all
# read as "full stop, long silence".
BEAT = " — "

_CLOSING = re.compile(r"^\s*(goodnight|good night|sleep well|sweet dreams)", re.I)

# Openers that signal a genuine jump rather than the next sentence along.
_SCENE_SHIFT = re.compile(
    r"^\s*(that (night|evening|morning)|the next|later|by (lunch|then|morning)|"
    r"on the \w+ day|at (home|the top|last)|then the|weeks? (later|of)|"
    r"nothing else happened|so |but on)", re.I)

NARRATION_STYLE = (
    "Read this as a bedtime story to a sleepy child aged five to ten. "
    "Warm, unhurried, gentle - the way a parent reads at the end of the day. "
    "Let it flow: do not pause heavily between sentences, and keep each "
    "paragraph moving as one connected thought. Take a natural breath at the "
    "blank lines between paragraphs, not after every full stop. "
    "Slow down gradually through the last third, and read the final two lines "
    "very softly and slowly. Do not sound excited, and do not announce anything."
)


@dataclass
class NarrationScript:
    text: str
    segments: List[str] = field(default_factory=list)
    est_seconds: float = 0.0
    speed: float = 1.0
    instructions: str = NARRATION_STYLE

    @property
    def n_segments(self) -> int:
        return len(self.segments)


def build_script(story: str, title: str = "", base_speed: float = 0.92):
    """Light markup only. Paragraph breaks are preserved as-is."""
    paragraphs = [p.strip() for p in _PARA.split(story or "") if p.strip()]
    if not paragraphs:
        return NarrationScript(text="", segments=[], est_seconds=0.0, speed=base_speed)

    out: List[str] = []
    if title:
        out.append(f"{title}.{BEAT}")

    total = len(paragraphs)
    # Hard cap. Even "only at scene shifts" gave four beats in a seven-paragraph
    # story, which still reads as stop-start. The closing beat is the one that
    # matters; at most one mid-story beat, and only past the halfway mark.
    max_mid_beats = 1 if total >= 6 else 0
    mid_used = 0

    for i, para in enumerate(paragraphs):
        if i > 0 and _CLOSING.match(para):
            out.append(BEAT)
        elif (i > total // 2 and mid_used < max_mid_beats
              and _SCENE_SHIFT.match(para)):
            out.append(BEAT)
            mid_used += 1
        out.append(para)

    # Two newlines between paragraphs: the engine already reads that as breath,
    # and it does it better than any punctuation trick.
    text = "\n\n".join(p for p in out if p.strip())

    words = len(_WORD.findall(story))
    est = (words / (150 * base_speed)) * 60 + total * 0.6

    return NarrationScript(text=text, segments=paragraphs, est_seconds=round(est, 1),
                           speed=base_speed, instructions=NARRATION_STYLE)


def split_for_tts(text: str, max_chars: int = 3800):
    if len(text) <= max_chars:
        return [text]

    chunks: List[str] = []
    current: List[str] = []
    size = 0
    for para in text.split("\n\n"):
        if size + len(para) + 2 > max_chars and current:
            chunks.append("\n\n".join(current))
            current, size = [], 0
        current.append(para)
        size += len(para) + 2
    if current:
        chunks.append("\n\n".join(current))
    return chunks
