"""SQLite chunk store with brute-force cosine search.

O(n) per query, which is fine to roughly 50k chunks. Past that it needs a real
ANN index.
"""

import json
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from ..storage import connect, probe
from .chunker import Chunk
from .embeddings import cosine, pack, unpack

SCHEMA = """
CREATE TABLE IF NOT EXISTS stories (
    story_id   TEXT PRIMARY KEY,
    run_id     TEXT,
    title      TEXT NOT NULL,
    story      TEXT NOT NULL,
    request    TEXT,
    category   TEXT,
    characters TEXT,
    composite  REAL,
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id   TEXT PRIMARY KEY,
    story_id   TEXT NOT NULL REFERENCES stories(story_id) ON DELETE CASCADE,
    kind       TEXT NOT NULL,
    ordinal    INTEGER NOT NULL,
    text       TEXT NOT NULL,
    word_count INTEGER NOT NULL,
    metadata   TEXT,
    vector     BLOB,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunks_story ON chunks(story_id);
CREATE INDEX IF NOT EXISTS idx_chunks_kind  ON chunks(kind);
CREATE INDEX IF NOT EXISTS idx_stories_time ON stories(created_at DESC);
"""

@dataclass
class Hit:
    chunk_id: str
    story_id: str
    kind: str
    text: str
    score: float
    title: str = ""
    created_at: float = 0.0
    metadata: Dict[str, Any] = None  # type: ignore[assignment]


class MemoryStore:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        probe(self.db_path, foreign_keys=True)   # raises StorageUnavailable
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def _connect(self):
        return connect(self.db_path, foreign_keys=True)

    # writes
    def add_story(self, story_id: str, title: str, story: str, chunks: List[Chunk],
                  vectors: Sequence[Sequence[float]], *, run_id: str = "",
                  request: str = "", category: str = "", characters: Optional[List[str]] = None,
                  composite: Optional[float] = None) -> None:
        """Insert or replace a story and its chunks."""
        now = time.time()
        rows = [
            (c.chunk_id, c.story_id, c.kind, c.ordinal, c.text, c.word_count,
             json.dumps(c.metadata), pack(v) if v else None, now)
            for c, v in zip(chunks, vectors)
        ]
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO stories VALUES (?,?,?,?,?,?,?,?,?)",
                (story_id, run_id, title, story, request, category,
                 json.dumps(characters or []), composite, now))
            conn.execute("DELETE FROM chunks WHERE story_id = ?", (story_id,))
            conn.executemany("INSERT INTO chunks VALUES (?,?,?,?,?,?,?,?,?)", rows)
        METRICS.inc("memory_stories_indexed_total")
        METRICS.add("memory_chunks_indexed_total", len(rows))
        LOG.info("indexed story %s (%d chunks)", story_id, len(rows))

    def forget(self, story_id: str) -> bool:
        """Delete a story and its chunks."""
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM stories WHERE story_id = ?", (story_id,))
            conn.execute("DELETE FROM chunks WHERE story_id = ?", (story_id,))
        return cur.rowcount > 0

    def clear(self):
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM chunks")
            conn.execute("DELETE FROM stories")

    # reads
    def search(self, query_vector: Sequence[float], top_k: int = 4,
               min_score: float = 0.35, kinds: Optional[Sequence[str]] = None,
               exclude_story_ids: Optional[Sequence[str]] = None) -> List[Hit]:
        """Cosine search over stored chunks."""
        started = time.perf_counter()
        sql = ("SELECT c.chunk_id, c.story_id, c.kind, c.text, c.metadata, c.vector, "
               "       s.title, s.created_at "
               "FROM chunks c JOIN stories s ON s.story_id = c.story_id "
               "WHERE c.vector IS NOT NULL")
        params: List[Any] = []
        if kinds:
            sql += f" AND c.kind IN ({','.join('?' * len(kinds))})"
            params.extend(kinds)
        if exclude_story_ids:
            sql += f" AND c.story_id NOT IN ({','.join('?' * len(exclude_story_ids))})"
            params.extend(exclude_story_ids)

        # NOTE: full scan. Fine at a few thousand chunks, needs an index past ~50k.
        hits: List[Hit] = []
        with self._lock, self._connect() as conn:
            for cid, sid, kind, text, meta, blob, title, created in conn.execute(sql, params):
                score = cosine(query_vector, unpack(blob))
                if score >= min_score:
                    hits.append(Hit(chunk_id=cid, story_id=sid, kind=kind, text=text,
                                    score=round(score, 4), title=title or "",
                                    created_at=created or 0.0,
                                    metadata=json.loads(meta or "{}")))

        hits.sort(key=lambda h: h.score, reverse=True)
        METRICS.observe("memory_search_seconds", time.perf_counter() - started)
        METRICS.inc("memory_searches_total", hit=str(bool(hits)).lower())
        return hits[:top_k]

    def get_story(self, story_id: str):
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT story_id, run_id, title, story, request, category, characters, "
                "composite, created_at FROM stories WHERE story_id = ?", (story_id,)).fetchone()
        if not row:
            return None
        keys = ["story_id", "run_id", "title", "story", "request", "category",
                "characters", "composite", "created_at"]
        out = dict(zip(keys, row))
        out["characters"] = json.loads(out["characters"] or "[]")
        return out

    def recent(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT story_id, title, request, category, composite, created_at "
                "FROM stories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        keys = ["story_id", "title", "request", "category", "composite", "created_at"]
        return [dict(zip(keys, r)) for r in rows]

    def find_by_character(self, name: str, limit: int = 5):
        """Exact name lookup. Runs alongside vector search, not instead of it."""
        needle = f"%{name.lower()}%"
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT story_id, title, request, category, composite, created_at "
                "FROM stories WHERE lower(characters) LIKE ? OR lower(title) LIKE ? "
                "ORDER BY created_at DESC LIMIT ?", (needle, needle, limit)).fetchall()
        keys = ["story_id", "title", "request", "category", "composite", "created_at"]
        return [dict(zip(keys, r)) for r in rows]

    def stats(self):
        with self._lock, self._connect() as conn:
            stories = conn.execute("SELECT COUNT(*) FROM stories").fetchone()[0]
            chunks = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
            vectors = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE vector IS NOT NULL").fetchone()[0]
        size = self.db_path.stat().st_size if self.db_path.exists() else 0
        return {
            "stories": stories,
            "chunks": chunks,
            "vectors": vectors,
            "db_bytes": size,
            "db_path": str(self.db_path),
            # Brute-force scan stays comfortable to roughly here.
            "scan_headroom": "fine" if chunks < 50_000 else "consider an ANN index",
        }
