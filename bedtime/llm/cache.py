"""SQLite cache with three namespaces: llm, plan, story.

Keys include the model and PROMPT_VERSION so a prompt edit invalidates the
affected entries. Story-level caching is off by default - see config.
"""

import hashlib
import json
import re
import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from ..storage import StorageUnavailable, connect, probe

SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key            TEXT PRIMARY KEY,
    namespace      TEXT NOT NULL,
    payload        TEXT NOT NULL,
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    created_at     REAL NOT NULL,
    expires_at     REAL NOT NULL,
    hits           INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_cache_ns      ON cache(namespace);
CREATE INDEX IF NOT EXISTS idx_cache_expires ON cache(expires_at);
"""
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s]")


def normalise(text: str) -> str:
    t = _PUNCT.sub(" ", (text or "").lower())
    t = _WS.sub(" ", t).strip()
    filler = ("please", "can you", "could you", "i want", "tell me", "a story about",
              "story about", "tell a story", "make up", "a story", "story")
    for f in filler:
        t = t.replace(f, " ")
    return _WS.sub(" ", t).strip()


@dataclass
class CacheStats:
    hits: int = 0
    misses: int = 0
    writes: int = 0

    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return round(self.hits / total, 4) if total else 0.0


class PersistentCache:
    def __init__(self, db_path: Path, model: str, prompt_version: str,
                 ttl_days: float = 14.0, enabled: bool = True):
        self.db_path = Path(db_path)
        self.model = model
        self.prompt_version = prompt_version
        self.ttl_seconds = ttl_days * 86400
        self.enabled = enabled
        self._lock = threading.Lock()
        self._stats: Dict[str, CacheStats] = {}
        if self.enabled:
            try:
                probe(self.db_path)
                with self._connect() as conn:
                    conn.executescript(SCHEMA)
                self.purge_expired()
            except (StorageUnavailable, sqlite3.Error, OSError) as exc:
                # A cache that cannot be written is just a slower system.
                LOG.warning("cache disabled - %s", exc)
                self.enabled = False

    def _connect(self):
        return connect(self.db_path)

    def _stat(self, namespace: str):
        return self._stats.setdefault(namespace, CacheStats())

    def key(self, namespace: str, *parts: Any) -> str:
        material = json.dumps(
            {"ns": namespace, "model": self.model, "pv": self.prompt_version,
             "parts": [str(p) for p in parts]},
            sort_keys=True)
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, namespace: str, key: str):
        """Look up a cache entry. Returns None on miss, expiry or any error."""
        if not self.enabled:
            return None
        now = time.time()
        try:
            with self._lock, self._connect() as conn:
                row = conn.execute(
                    "SELECT payload, expires_at FROM cache WHERE key = ? AND namespace = ?",
                    (key, namespace)).fetchone()
                if row and row[1] > now:
                    conn.execute("UPDATE cache SET hits = hits + 1 WHERE key = ?", (key,))
                    self._stat(namespace).hits += 1
                    METRICS.inc("cache_hits_total", namespace=namespace)
                    return json.loads(row[0])
                if row:
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
        except (sqlite3.Error, json.JSONDecodeError) as exc:
            # A broken cache must never break a request.
            LOG.warning("cache read failed (%s): %s", namespace, exc)
            METRICS.inc("cache_errors_total", op="read")
            return None

        self._stat(namespace).misses += 1
        METRICS.inc("cache_misses_total", namespace=namespace)
        return None

    def put(self, namespace: str, key: str, payload: Any,
            ttl_seconds: Optional[float] = None) -> None:
        """Write a cache entry."""
        if not self.enabled:
            return
        now = time.time()
        expires = now + (ttl_seconds if ttl_seconds is not None else self.ttl_seconds)
        try:
            with self._lock, self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO cache "
                    "(key, namespace, payload, model, prompt_version, created_at, expires_at, hits) "
                    "VALUES (?,?,?,?,?,?,?,0)",
                    (key, namespace, json.dumps(payload, default=str),
                     self.model, self.prompt_version, now, expires))
            self._stat(namespace).writes += 1
            METRICS.inc("cache_writes_total", namespace=namespace)
        except sqlite3.Error as exc:
            LOG.warning("cache write failed (%s): %s", namespace, exc)
            METRICS.inc("cache_errors_total", op="write")

    # -- maintenance --------------------------------------------------------
    def purge_expired(self) -> int:
        if not self.enabled:
            return 0
        try:
            with self._lock, self._connect() as conn:
                cur = conn.execute("DELETE FROM cache WHERE expires_at < ?", (time.time(),))
            return cur.rowcount
        except sqlite3.Error:
            return 0

    def invalidate(self, namespace: Optional[str] = None):
        if not self.enabled:
            return 0
        with self._lock, self._connect() as conn:
            if namespace:
                cur = conn.execute("DELETE FROM cache WHERE namespace = ?", (namespace,))
            else:
                cur = conn.execute("DELETE FROM cache")
        return cur.rowcount

    def invalidate_stale_versions(self):
        """Drop anything written under a different prompt version or model."""
        if not self.enabled:
            return 0
        with self._lock, self._connect() as conn:
            cur = conn.execute(
                "DELETE FROM cache WHERE prompt_version != ? OR model != ?",
                (self.prompt_version, self.model))
        if cur.rowcount:
            LOG.info("invalidated %d cache entries from an older prompt/model version",
                     cur.rowcount)
        return cur.rowcount

    def stats(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {
            "enabled": self.enabled,
            "path": str(self.db_path),
            "prompt_version": self.prompt_version,
            "namespaces": {ns: {"hits": s.hits, "misses": s.misses,
                                "writes": s.writes, "hit_rate": s.hit_rate}
                           for ns, s in self._stats.items()},
        }
        if not self.enabled:
            return out
        try:
            with self._lock, self._connect() as conn:
                rows = conn.execute(
                    "SELECT namespace, COUNT(*), COALESCE(SUM(hits),0) "
                    "FROM cache GROUP BY namespace").fetchall()
            out["stored"] = {ns: {"entries": n, "served": h} for ns, n, h in rows}
            out["db_bytes"] = self.db_path.stat().st_size if self.db_path.exists() else 0
        except sqlite3.Error:
            pass
        return out

    # typed helpers
    def llm_key(self, system: str, user: str, temperature: float, max_tokens: int,
                json_mode: bool, seed: Optional[int]) -> str:
        return self.key("llm", system, user, round(temperature, 3), max_tokens,
                        json_mode, seed)

    def plan_key(self, brief) -> str:
        """Keyed on the *shape* of the request, not its wording."""
        return self.key(
            "plan",
            getattr(getattr(brief, "category", None), "value", ""),
            "|".join(sorted(c.lower() for c in (getattr(brief, "characters", []) or []))),
            "|".join(sorted(t.lower() for t in (getattr(brief, "themes", []) or []))),
            getattr(brief, "tone", ""),
            getattr(brief, "target_age", 7),
            normalise(getattr(brief, "sanitized_request", "")),
        )

    def story_key(self, request: str) -> str:
        return self.key("story", normalise(request))
