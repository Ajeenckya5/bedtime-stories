"""Rate limiter, circuit breaker, budget guard, LRU cache."""

from __future__ import annotations

import hashlib
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Dict, Optional, Tuple

from ..errors import BudgetExceededError, CircuitOpenError


class TokenBucket:
    """Classic token bucket. Smooths bursts instead of hard-failing them.

    `acquire` blocks (up to `timeout`) rather than raising, because a bedtime
    story that arrives 400ms late is fine; one that errors is not.
    """
    def __init__(self, rate_per_minute: int, burst: Optional[int] = None):
        self.capacity = float(burst or max(1, rate_per_minute))
        self.tokens = self.capacity
        self.refill_per_s = rate_per_minute / 60.0
        self._last = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self._last
        self._last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_s)

    def acquire(self, timeout: float = 30.0):
        """Block until a token is free, or return False on timeout."""
        deadline = time.monotonic() + timeout
        while True:
            with self._lock:
                self._refill()
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return True
                deficit = 1.0 - self.tokens
                wait = deficit / self.refill_per_s if self.refill_per_s else timeout
            if time.monotonic() + wait > deadline:
                return False
            time.sleep(min(wait, 0.25))

    def try_acquire(self):
        with self._lock:
            self._refill()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class CircuitBreaker:
    """Three-state breaker: closed -> open -> half-open -> closed.

    Once the upstream has failed `fail_threshold` times we stop calling it for
    `reset_after_s`. This turns a 45s timeout per request into an instant,
    cheap failure and lets the provider recover instead of being hammered.
    """
    CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"

    def __init__(self, fail_threshold: int = 5, reset_after_s: float = 30.0):
        self.fail_threshold = fail_threshold
        self.reset_after_s = reset_after_s
        self._failures = 0
        self._state = self.CLOSED
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self):
        with self._lock:
            self._maybe_half_open()
            return self._state

    def _maybe_half_open(self):
        if self._state == self.OPEN and time.monotonic() - self._opened_at >= self.reset_after_s:
            self._state = self.HALF_OPEN

    def before_call(self):
        with self._lock:
            self._maybe_half_open()
            if self._state == self.OPEN:
                remaining = self.reset_after_s - (time.monotonic() - self._opened_at)
                raise CircuitOpenError(f"circuit open, retry in {remaining:.1f}s")

    def on_success(self):
        with self._lock:
            self._failures = 0
            self._state = self.CLOSED

    def on_failure(self):
        with self._lock:
            self._failures += 1
            if self._state == self.HALF_OPEN or self._failures >= self.fail_threshold:
                self._state = self.OPEN
                self._opened_at = time.monotonic()


@dataclass
class BudgetGuard:
    """Two-level spend cap: per run and per UTC day.

    The per-run cap is the important one - it bounds the blast radius of a
    revision loop that refuses to converge.
    """
    max_usd_per_run: float = 0.25
    max_usd_per_day: float = 25.0
    _day: str = field(default_factory=lambda: date.today().isoformat())
    _day_spend: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def check_and_add(self, run_spend: float, delta: float):
        with self._lock:
            today = date.today().isoformat()
            if today != self._day:
                self._day, self._day_spend = today, 0.0
            if run_spend + delta > self.max_usd_per_run:
                raise BudgetExceededError(
                    f"per-run budget exceeded: ${run_spend + delta:.4f} > ${self.max_usd_per_run:.4f}"
                )
            if self._day_spend + delta > self.max_usd_per_day:
                raise BudgetExceededError(
                    f"daily budget exceeded: ${self._day_spend + delta:.4f} > ${self.max_usd_per_day:.2f}"
                )
            self._day_spend += delta

    @property
    def day_spend(self) -> float:
        with self._lock:
            return self._day_spend


class PromptCache:
    """Content-addressed LRU over (prompt, params).

    Only safe for deterministic calls, so the provider bypasses it whenever
    temperature > 0 unless an explicit seed is set. Classifier and judge calls
    at temperature 0 hit it constantly during evals - a large real saving.
    """
    def __init__(self, max_entries: int = 512):
        self._data: "OrderedDict[str, object]" = OrderedDict()
        self.max_entries = max_entries
        self.hits = 0
        self.misses = 0
        self._lock = threading.Lock()

    @staticmethod
    def key(material: str) -> str:
        return hashlib.sha256(material.encode("utf-8")).hexdigest()

    def get(self, key: str):
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                self.hits += 1
                return self._data[key]
            self.misses += 1
            return None

    def put(self, key: str, value: object):
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.max_entries:
                self._data.popitem(last=False)

    def stats(self) -> Dict[str, float]:
        total = self.hits + self.misses
        return {
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(self.hits / total, 3) if total else 0.0,
            "size": len(self._data),
        }


def retry_with_backoff(
    fn: Callable[[], object],
    *,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    retry_on: Tuple[type, ...],
    on_retry: Optional[Callable[[int, BaseException, float], None]] = None,
    jitter: Callable[[], float] = lambda: 0.0,
):
    last: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fn()
        except retry_on as exc:  # type: ignore[misc]
            last = exc
            if attempt == max_attempts:
                break
            delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
            delay += jitter() * delay
            if on_retry:
                on_retry(attempt, exc, delay)
            time.sleep(delay)
    assert last is not None
    raise last
