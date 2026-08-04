"""One JSONL line per run with nested spans. Never contains the API key."""

import json
import logging
import os
import sys
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

_LOCK = threading.Lock()


def configure_logging(level: str = "INFO"):
    logger = logging.getLogger("bedtime")
    if logger.handlers:
        logger.setLevel(getattr(logging, level.upper(), logging.INFO))
        return logger
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s | %(message)s", "%H:%M:%S"))
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    logger.propagate = False
    return logger


LOG = configure_logging(os.getenv("BEDTIME_LOG_LEVEL", "INFO"))


@dataclass
class Span:
    name: str
    started_at: float
    ended_at: float = 0.0
    status: str = "ok"
    attributes: Dict[str, Any] = field(default_factory=dict)
    events: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_s(self) -> float:
        return round((self.ended_at or time.time()) - self.started_at, 4)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "duration_s": self.duration_s,
            "status": self.status,
            "attributes": self.attributes,
            "events": self.events,
        }


class RunTrace:
    """Collects everything about one story run and writes it atomically."""
    def __init__(self, run_id: Optional[str] = None, trace_dir: Optional[Path] = None,
                 redact_text: bool = False, metadata: Optional[Dict[str, Any]] = None):
        self.run_id = run_id or f"run_{uuid.uuid4().hex[:12]}"
        self.trace_dir = Path(trace_dir) if trace_dir else Path("traces")
        self.redact_text = redact_text
        self.started_at = time.time()
        self.spans: List[Span] = []
        self.metadata: Dict[str, Any] = metadata or {}
        self.result_summary: Dict[str, Any] = {}
        self._stack: List[Span] = []

    @contextmanager
    def span(self, name: str, **attributes: Any) -> Iterator[Span]:
        """Time a stage and attach it to the run trace."""
        s = Span(name=name, started_at=time.time(), attributes=dict(attributes))
        self.spans.append(s)
        self._stack.append(s)
        LOG.debug("[%s] -> %s", self.run_id, name)
        try:
            yield s
        except Exception as exc:
            s.status = "error"
            s.attributes["error_type"] = type(exc).__name__
            s.attributes["error"] = str(exc)[:500]
            raise
        finally:
            s.ended_at = time.time()
            self._stack.pop()
            LOG.debug("[%s] <- %s (%.2fs, %s)", self.run_id, name, s.duration_s, s.status)

    def event(self, message: str, **fields: Any):
        payload = {"t": round(time.time() - self.started_at, 4), "message": message, **fields}
        (self._stack[-1].events if self._stack else self.metadata.setdefault("events", [])).append(payload)
        LOG.info("[%s] %s %s", self.run_id, message,
                 " ".join(f"{k}={v}" for k, v in fields.items()) if fields else "")

    def set_result(self, summary: Dict[str, Any]) -> None:
        self.result_summary = summary

    def to_dict(self):
        return {
            "run_id": self.run_id,
            "ts": self.started_at,
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(self.started_at)),
            "duration_s": round(time.time() - self.started_at, 4),
            "metadata": self.metadata,
            "result": self.result_summary,
            "spans": [s.to_dict() for s in self.spans],
        }

    def write(self):
        try:
            self.trace_dir.mkdir(parents=True, exist_ok=True)
            path = self.trace_dir / f"{time.strftime('%Y-%m-%d', time.gmtime(self.started_at))}.jsonl"
            line = json.dumps(self.to_dict(), ensure_ascii=False, default=str)
            with _LOCK:
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
            return path
        except OSError as exc:  # tracing must never break the request path
            LOG.warning("trace write failed: %s", exc)
            return None


def read_traces(trace_dir: Path, limit: int = 2000) -> List[Dict[str, Any]]:
    trace_dir = Path(trace_dir)
    if not trace_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in sorted(trace_dir.glob("*.jsonl"), reverse=True):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
                if len(rows) >= limit:
                    return rows
        except OSError:
            continue
    return rows
