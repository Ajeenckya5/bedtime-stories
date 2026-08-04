"""Retrieval + building the continuity block for the prompts.

Hybrid: exact character-name lookup alongside vector search. Context is capped
and explicitly framed as background, or gpt-3.5 just retells the old story.
"""

import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence

from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from .chunker import chunk_story
from .embeddings import Embedder, build_embedder
from .store import Hit, MemoryStore

# Phrases that mean "you have told me a story before, use it".
_CONTINUITY_MARKERS = re.compile(
    r"\b(again|another one|more about|same|last (time|night|week)|"
    r"you told|remember|sequel|next (story|adventure)|continue|"
    r"like the .{0,20}(one|story)|what happened (next|after))\b", re.I)


@dataclass
class Continuity:
    """What the planner and storyteller get told about the past."""
    hits: List[Hit] = field(default_factory=list)
    stories: List[Dict[str, Any]] = field(default_factory=list)
    requested_explicitly: bool = False
    block: str = ""

    @property
    def found(self):
        return bool(self.block)

    def summary(self):
        return {
            "n_hits": len(self.hits),
            "n_stories": len(self.stories),
            "explicit": self.requested_explicitly,
            "top_score": round(self.hits[0].score, 3) if self.hits else 0.0,
            "titles": [s.get("title", "") for s in self.stories][:3],
            "words": len(self.block.split()),
        }


class Retriever:
    def __init__(self, settings, store: Optional[MemoryStore] = None,
                 embedder: Optional[Embedder] = None):
        self.settings = settings
        self.store = store or MemoryStore(settings.memory_db)
        self.embedder = embedder or build_embedder(settings)

    # read path
    def recall(self, request: str, characters: Optional[Sequence[str]] = None,
               trace=None) -> Continuity:
        """Find relevant past stories and build the continuity block."""
        if not self.settings.memory_enabled:
            return Continuity()

        explicit = bool(_CONTINUITY_MARKERS.search(request or ""))
        # A vague request with no continuity cue and no known name gets nothing.
        # Injecting a random past story into every request makes the output
        # worse, not better.
        name_hits = self._by_name(characters or [])
        base = self._similarity_floor()
        threshold = base if (explicit or name_hits) else max(base * 1.5, base + 0.15)

        started = time.perf_counter()
        try:
            query_vec = self.embedder.embed([request])[0]
        except Exception as exc:
            LOG.warning("recall embedding failed: %s", exc)
            return Continuity(requested_explicitly=explicit)

        hits = self.store.search(
            query_vec,
            top_k=self.settings.memory_top_k,
            min_score=threshold,
            kinds=("card", "scene"),
        )

        # Promote name matches that vector search missed.
        known = {h.story_id for h in hits}
        for row in name_hits:
            if row["story_id"] not in known:
                card = self._card_for(row["story_id"])
                if card:
                    card.score = max(card.score, 0.99)  # exact name beats cosine
                    hits.insert(0, card)
                    known.add(row["story_id"])

        hits = hits[: self.settings.memory_top_k]
        stories = [s for s in (self.store.get_story(sid) for sid in
                               dict.fromkeys(h.story_id for h in hits)) if s]

        continuity = Continuity(hits=hits, stories=stories, requested_explicitly=explicit)
        continuity.block = self._render(continuity)

        METRICS.observe("memory_recall_seconds", time.perf_counter() - started)
        if trace is not None and continuity.found:
            trace.event("memory_recalled", **continuity.summary())
        return continuity

    def _similarity_floor(self) -> float:
        if "tfidf" in self.embedder.name:
            return min(self.settings.memory_min_similarity, 0.12)
        return self.settings.memory_min_similarity

    def _by_name(self, characters: Sequence[str]):
        out: List[Dict[str, Any]] = []
        seen = set()
        for name in characters:
            first = (name or "").split()[0].strip(",.") if name else ""
            if len(first) < 3:
                continue
            for row in self.store.find_by_character(first, limit=3):
                if row["story_id"] not in seen:
                    seen.add(row["story_id"])
                    out.append(row)
        return out

    def _card_for(self, story_id: str) -> Optional[Hit]:
        story = self.store.get_story(story_id)
        if not story:
            return None
        return Hit(chunk_id=f"{story_id}:card:0", story_id=story_id, kind="card",
                   text=f"Title: {story['title']}\nOriginally asked for: {story.get('request', '')}",
                   score=0.99, title=story["title"], created_at=story.get("created_at", 0.0),
                   metadata={})

    def _render(self, continuity: Continuity):
        if not continuity.hits:
            return ""
        budget = self.settings.memory_context_words
        lines = [
            "You have told this family stories before. Below are the relevant "
            "details from those stories.",
            "Keep names, personalities and established facts CONSISTENT with these. "
            "Do NOT retell any of it - this is background, and the new story must "
            "stand on its own and have its own arc.",
            "",
        ]
        used = 0
        for hit in continuity.hits:
            words = hit.text.split()
            if used + len(words) > budget:
                words = words[: max(0, budget - used)]
                if len(words) < 20:
                    break
            snippet = " ".join(words)
            label = "Story summary" if hit.kind == "card" else "Scene from a past story"
            lines.append(f"[{label} - \"{hit.title}\"]\n{snippet}")
            lines.append("")
            used += len(words)
            if used >= budget:
                break
        return "\n".join(lines).strip()

    # -- write path ---------------------------------------------------------
    def remember(self, *, story_id: str, run_id: str, title: str, story: str,
                 brief=None, plan=None, composite: Optional[float] = None,
                 trace=None) -> int:
        """Index a released story. Returns the number of chunks stored."""
        if not self.settings.memory_enabled or not story:
            return 0
        try:
            chunks = chunk_story(
                story_id, title, story, brief, plan,
                target_words=self.settings.memory_chunk_words,
                overlap_words=self.settings.memory_chunk_overlap,
            )
            vectors = self.embedder.embed([c.text for c in chunks])
            self.store.add_story(
                story_id=story_id, title=title, story=story, chunks=chunks,
                vectors=vectors, run_id=run_id,
                request=getattr(brief, "raw_request", "") if brief else "",
                category=getattr(getattr(brief, "category", None), "value", "") if brief else "",
                characters=list(getattr(brief, "characters", []) or []) if brief else [],
                composite=composite,
            )
            if trace is not None:
                trace.event("memory_indexed", story_id=story_id, chunks=len(chunks))
            return len(chunks)
        except Exception as exc:
            # Memory is an enhancement. Failing to index must never fail a run
            # that already produced a good story.
            LOG.warning("failed to index story %s: %s", story_id, exc)
            METRICS.inc("memory_index_errors_total", error=type(exc).__name__)
            if trace is not None:
                trace.event("memory_index_failed", error=str(exc)[:160])
            return 0

    def stats(self):
        out = self.store.stats()
        out["embedder"] = self.embedder.name
        out["dim"] = self.embedder.dim
        return out
