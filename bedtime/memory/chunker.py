"""Splits a story into retrievable pieces.

One "card" per story (title, characters, opening/closing) plus overlapping
paragraph "scenes". Paragraph boundaries are kept - splitting mid-paragraph
gives you chunks that retrieve fine and read as nonsense in a prompt.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

_PARA_SPLIT = re.compile(r"\n\s*\n")
_WORD = re.compile(r"[A-Za-z][A-Za-z'-]*")


@dataclass
class Chunk:
    story_id: str
    kind: str                 # "card" | "scene"
    ordinal: int
    text: str
    word_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_id(self):
        return f"{self.story_id}:{self.kind}:{self.ordinal}"


def _words(text: str):
    return len(_WORD.findall(text or ""))


def paragraphs(text: str) -> List[str]:
    return [p.strip() for p in _PARA_SPLIT.split(text or "") if p.strip()]


def make_card(story_id: str, title: str, story: str, brief=None, plan=None) -> Chunk:
    bits: List[str] = [f"Title: {title}"]
    if plan is not None:
        bits.append(f"About: {getattr(plan, 'logline', '')}")
        bits.append(f"Main character: {getattr(plan, 'protagonist', '')}")
        motifs = getattr(plan, "sensory_motifs", None) or []
        if motifs:
            bits.append("Recurring images: " + ", ".join(motifs))
        if getattr(plan, "lesson", ""):
            bits.append(f"Feeling it leaves: {plan.lesson}")
    if brief is not None:
        chars = getattr(brief, "characters", None) or []
        if chars:
            bits.append("Characters: " + ", ".join(chars))
        if getattr(brief, "setting", ""):
            bits.append(f"Setting: {brief.setting}")
        themes = getattr(brief, "themes", None) or []
        if themes:
            bits.append("Themes: " + ", ".join(themes))
        if getattr(brief, "category", None) is not None:
            bits.append(f"Kind of story: {brief.category.value}")
        if getattr(brief, "raw_request", ""):
            bits.append(f"Originally asked for: {brief.raw_request}")

    # First and last paragraph carry the opening image and the settled ending,
    # which is often exactly what someone is trying to recall.
    paras = paragraphs(story)
    if paras:
        bits.append(f"Opens with: {paras[0][:220]}")
    if len(paras) > 1:
        bits.append(f"Ends with: {paras[-1][:220]}")

    text = "\n".join(b for b in bits if b and not b.endswith(": "))
    return Chunk(story_id=story_id, kind="card", ordinal=0, text=text,
                 word_count=_words(text), metadata={"title": title})


def make_scenes(story_id: str, story: str, target_words: int = 120,
                overlap_words: int = 30, title: str = "") -> List[Chunk]:
    """Overlapping paragraph windows of roughly target_words each."""
    paras = paragraphs(story)
    if not paras:
        return []

    chunks: List[Chunk] = []
    window: List[str] = []
    window_words = 0
    ordinal = 0

    def flush() -> None:
        nonlocal window, window_words, ordinal
        if not window:
            return
        text = "\n\n".join(window)
        chunks.append(Chunk(story_id=story_id, kind="scene", ordinal=ordinal,
                            text=text, word_count=_words(text),
                            metadata={"title": title, "paragraphs": len(window)}))
        ordinal += 1
        # Carry the tail paragraphs forward as the overlap.
        carried: List[str] = []
        carried_words = 0
        for p in reversed(window):
            if carried_words >= overlap_words:
                break
            carried.insert(0, p)
            carried_words += _words(p)
        window = carried if len(carried) < len(window) else []
        window_words = sum(_words(p) for p in window)

    for para in paras:
        pw = _words(para)
        # A single paragraph longer than the window becomes its own chunk
        # rather than being cut mid-thought.
        if pw > target_words * 1.6:
            flush()
            chunks.append(Chunk(story_id=story_id, kind="scene", ordinal=ordinal,
                                text=para, word_count=pw,
                                metadata={"title": title, "paragraphs": 1, "oversized": True}))
            ordinal += 1
            window, window_words = [], 0
            continue
        if window_words + pw > target_words and window:
            flush()
        window.append(para)
        window_words += pw

    flush()
    # Drop a trailing chunk that is pure overlap of the previous one.
    if len(chunks) >= 2 and chunks[-1].text in chunks[-2].text:
        chunks.pop()
    return chunks


def chunk_story(story_id: str, title: str, story: str, brief=None, plan=None,
                target_words: int = 120, overlap_words: int = 30) -> List[Chunk]:
    """Split a story into one card chunk plus overlapping scene chunks."""
    card = make_card(story_id, title, story, brief, plan)
    scenes = make_scenes(story_id, story, target_words, overlap_words, title)
    return [card] + scenes
