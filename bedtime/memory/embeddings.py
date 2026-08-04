"""Embedding backends: OpenAI, or a stdlib TF-IDF fallback.

Vectors are cached in SQLite by content hash.
"""

import hashlib
import math
import re
import sqlite3
import struct
import threading
from collections import Counter
from pathlib import Path
from typing import Dict, List, Optional, Protocol, Sequence

from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from ..storage import connect

_WORD = re.compile(r"[a-z][a-z'-]+")
_STOP = {
    "the", "and", "was", "for", "with", "that", "this", "she", "her", "his",
    "him", "they", "them", "their", "had", "has", "have", "were", "are", "but",
    "not", "you", "your", "all", "one", "out", "who", "into", "then", "than",
    "there", "here", "what", "when", "very", "just", "from", "about", "would",
    "could", "said", "says", "like", "some", "more", "only", "over", "back",
}


def text_hash(text: str, model: str):
    return hashlib.sha256(f"{model}\x00{text}".encode("utf-8")).hexdigest()


def pack(vec: Sequence[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def unpack(blob: bytes) -> List[float]:
    return list(struct.unpack(f"<{len(blob) // 4}f", blob))


# Plain python. Tried numpy first, it wasn't worth the dependency at this size.
def cosine(a: Sequence[float], b: Sequence[float]):
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = na = nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / math.sqrt(na * nb)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: List[str]) -> List[List[float]]: ...


class TfidfEmbedder:
    """Hashing-trick TF-IDF. Fixed dimensionality, no vocabulary to persist.

    Genuinely weaker than a real encoder - it cannot tell that "dragon" and
    "wyvern" are related - but it matches names and concrete nouns well, and
    those dominate the queries this system actually gets.
    """
    name = "tfidf"

    def __init__(self, dim: int = 512) -> None:
        self.dim = dim

    @staticmethod
    def _tokens(text: str):
        return [w for w in _WORD.findall((text or "").lower())
                if len(w) > 2 and w not in _STOP]

    def embed(self, texts: List[str]):
        docs = [self._tokens(t) for t in texts]
        # Document frequency across this batch only. Approximate, but it is a
        # fallback path and it keeps the embedder stateless.
        df: Counter = Counter()
        for toks in docs:
            df.update(set(toks))
        n = max(1, len(docs))

        out: List[List[float]] = []
        for toks in docs:
            vec = [0.0] * self.dim
            if not toks:
                out.append(vec)
                continue
            tf = Counter(toks)
            for term, count in tf.items():
                idf = math.log((n + 1) / (df[term] + 1)) + 1.0
                weight = (1 + math.log(count)) * idf
                h = int(hashlib.md5(term.encode()).hexdigest()[:8], 16)
                # Signed hashing reduces collision bias.
                sign = 1.0 if (h >> 31) & 1 == 0 else -1.0
                vec[h % self.dim] += sign * weight
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            out.append([v / norm for v in vec])
        return out


class OpenAIEmbedder:
    """text-embedding-3-small, batched, with graceful degradation."""
    name = "openai"

    def __init__(self, api_key: str, model: str = "text-embedding-3-small",
                 dim: int = 1536, base_url: str = "", timeout: float = 30.0) -> None:
        self.model = model
        self.dim = dim
        self._fallback = TfidfEmbedder(dim=dim)
        self._client = None
        try:
            import openai  # type: ignore

            kwargs = {"api_key": api_key, "timeout": timeout, "max_retries": 2}
            if base_url:
                kwargs["base_url"] = base_url
            self._client = openai.OpenAI(**kwargs)
        except Exception as exc:  # pragma: no cover
            LOG.warning("openai embedder unavailable (%s); using tfidf", exc)

    def embed(self, texts: List[str]):
        if self._client is None or not texts:
            return self._fallback.embed(texts)
        try:
            resp = self._client.embeddings.create(
                model=self.model, input=[t[:8000] for t in texts])
            METRICS.inc("embedding_calls_total", model=self.model)
            METRICS.add("embedding_tokens_total",
                        getattr(getattr(resp, "usage", None), "total_tokens", 0) or 0)
            return [list(d.embedding) for d in resp.data]
        except Exception as exc:
            # Retrieval quality drops; the run does not fail.
            LOG.warning("embedding call failed (%s); falling back to tfidf", exc)
            METRICS.inc("embedding_errors_total", error=type(exc).__name__)
            return self._fallback.embed(texts)


class CachedEmbedder:
    """Wraps any embedder with a SQLite content-hash cache."""
    def __init__(self, inner: Embedder, db_path: Path):
        self.inner = inner
        self.name = f"cached:{inner.name}"
        self.dim = inner.dim
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self):
        return connect(self.db_path)

    def _init_db(self):
        with self._lock, self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embeddings (
                    hash TEXT PRIMARY KEY,
                    model TEXT NOT NULL,
                    dim INTEGER NOT NULL,
                    vector BLOB NOT NULL,
                    created_at REAL NOT NULL
                )""")

    def embed(self, texts: List[str]) -> List[List[float]]:
        import time

        model_tag = f"{self.inner.name}:{self.inner.dim}"
        hashes = [text_hash(t, model_tag) for t in texts]
        found: Dict[str, List[float]] = {}

        with self._lock, self._connect() as conn:
            placeholders = ",".join("?" * len(hashes)) or "''"
            for h, blob in conn.execute(
                    f"SELECT hash, vector FROM embeddings WHERE hash IN ({placeholders})", hashes):
                found[h] = unpack(blob)

        missing_idx = [i for i, h in enumerate(hashes) if h not in found]
        if missing_idx:
            fresh = self.inner.embed([texts[i] for i in missing_idx])
            now = time.time()
            rows = []
            for i, vec in zip(missing_idx, fresh):
                found[hashes[i]] = vec
                rows.append((hashes[i], model_tag, len(vec), pack(vec), now))
            with self._lock, self._connect() as conn:
                conn.executemany(
                    "INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?,?)", rows)

        METRICS.add("embedding_cache_hits_total", len(texts) - len(missing_idx))
        METRICS.add("embedding_cache_misses_total", len(missing_idx))
        return [found[h] for h in hashes]


def build_embedder(settings) -> Embedder:
    db = Path(settings.memory_db).with_name("embeddings.sqlite3")
    if settings.use_embeddings and settings.api_key:
        inner: Embedder = OpenAIEmbedder(
            api_key=settings.api_key,
            model=settings.embedding_model,
            dim=settings.embedding_dim,
            base_url=settings.base_url,
            timeout=settings.request_timeout_s,
        )
    else:
        inner = TfidfEmbedder(dim=512)
        if settings.use_embeddings:
            LOG.info("no API key - memory retrieval using the tfidf embedder")
    return CachedEmbedder(inner, db)
