"""Metrics registry with Prometheus text output. No external deps."""

import threading
import time
from collections import defaultdict
from typing import Dict, Iterable, List, Tuple

LabelKey = Tuple[Tuple[str, str], ...]

# Buckets chosen around observed pipeline latencies: a single call is ~1-6s,
# a full run with 3 judge samples and a revision is ~15-45s.
DEFAULT_BUCKETS: Tuple[float, ...] = (0.25, 0.5, 1, 2, 4, 8, 15, 30, 60, 120)
SCORE_BUCKETS: Tuple[float, ...] = (40, 55, 65, 70, 75, 80, 82, 85, 90, 95, 100)

HELP = {
    "llm_calls_total": "Chat completion calls issued, by pipeline stage.",
    "llm_errors_total": "Model calls that failed after all retries.",
    "llm_retries_total": "Individual retry attempts.",
    "llm_cache_hits_total": "Deterministic prompt cache hits.",
    "llm_rate_limited_total": "Calls rejected by the local rate limiter.",
    "llm_tokens_total": "Tokens consumed, by stage and kind.",
    "llm_cost_usd_total": "Estimated spend in USD.",
    "llm_json_mode_disabled_total": "Times response_format was rejected and disabled.",
    "llm_latency_seconds": "Latency of a single model call.",
    "moderation_checks_total": "Moderation API calls, by flagged outcome.",
    "moderation_unavailable_total": "Moderation calls that failed (fail-open).",
    "stories_total": "Completed story runs, by terminal status.",
    "story_latency_seconds": "End-to-end latency of a story run.",
    "story_quality_score": "Final composite quality score (0-100).",
    "story_revisions_total": "Revision cycles consumed, by outcome.",
    "guardrail_blocks_total": "Requests or outputs blocked, by guardrail and reason.",
    "judge_disagreement": "Normalised spread between judge samples (0=perfect agreement).",
    "gate_failures_total": "Quality-gate failures, by reason.",
    "fallback_served_total": "Times the curated safe fallback story was served.",
    "api_requests_total": "HTTP requests, by route and status class.",
}


class _Histogram:
    __slots__ = ("buckets", "counts", "sum", "count")

    def __init__(self, buckets: Iterable[float]):
        self.buckets = tuple(buckets)
        self.counts = [0] * (len(self.buckets) + 1)
        self.sum = 0.0
        self.count = 0

    def observe(self, value: float) -> None:
        self.sum += value
        self.count += 1
        for i, edge in enumerate(self.buckets):
            if value <= edge:
                self.counts[i] += 1
                return
        self.counts[-1] += 1

    def cumulative(self) -> List[int]:
        out, running = [], 0
        for c in self.counts[:-1]:
            running += c
            out.append(running)
        return out

    def quantile(self, q: float):
        if self.count == 0:
            return 0.0
        target = q * self.count
        running = 0
        for edge, c in zip(self.buckets, self.counts[:-1]):
            running += c
            if running >= target:
                return edge
        return float(self.buckets[-1])


class MetricsRegistry:
    def __init__(self):
        self._counters: Dict[str, Dict[LabelKey, float]] = defaultdict(dict)
        self._gauges: Dict[str, Dict[LabelKey, float]] = defaultdict(dict)
        self._hists: Dict[str, Dict[LabelKey, _Histogram]] = defaultdict(dict)
        self._lock = threading.Lock()
        self.started_at = time.time()

    @staticmethod
    def _key(labels: Dict[str, str]) -> LabelKey:
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def inc(self, name: str, value: float = 1.0, **labels: str):
        self.add(name, value, **labels)

    def add(self, name: str, value: float, **labels: str):
        k = self._key(labels)
        with self._lock:
            self._counters[name][k] = self._counters[name].get(k, 0.0) + value

    def gauge(self, name: str, value: float, **labels: str) -> None:
        with self._lock:
            self._gauges[name][self._key(labels)] = value

    def observe(self, name: str, value: float, **labels: str) -> None:
        k = self._key(labels)
        buckets = SCORE_BUCKETS if name.endswith("_score") else DEFAULT_BUCKETS
        with self._lock:
            if k not in self._hists[name]:
                self._hists[name][k] = _Histogram(buckets)
            self._hists[name][k].observe(value)

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return {
                "counters": {n: {dict(k).__str__(): v for k, v in s.items()}
                             for n, s in self._counters.items()},
                "gauges": {n: {dict(k).__str__(): v for k, v in s.items()}
                           for n, s in self._gauges.items()},
                "histograms": {
                    n: {
                        dict(k).__str__(): {
                            "count": h.count,
                            "sum": round(h.sum, 4),
                            "avg": round(h.sum / h.count, 4) if h.count else 0.0,
                            "p50": h.quantile(0.5),
                            "p95": h.quantile(0.95),
                        }
                        for k, h in s.items()
                    }
                    for n, s in self._hists.items()
                },
                "uptime_s": round(time.time() - self.started_at, 1),
            }

    def reset(self):
        with self._lock:
            self._counters.clear()
            self._gauges.clear()
            self._hists.clear()

    # -- exposition ---------------------------------------------------------
    @staticmethod
    def _fmt_labels(k: LabelKey, extra: Tuple[Tuple[str, str], ...] = ()) -> str:
        items = list(k) + list(extra)
        if not items:
            return ""
        inner = ",".join(
            f'{name}="{str(val).replace(chr(92), chr(92) * 2).replace(chr(34), chr(92) + chr(34))}"'
            for name, val in items
        )
        return "{" + inner + "}"

    def render_prometheus(self):
        """Prometheus text exposition format."""
        lines: List[str] = []
        with self._lock:
            for name, series in sorted(self._counters.items()):
                lines.append(f"# HELP {name} {HELP.get(name, name)}")
                lines.append(f"# TYPE {name} counter")
                for k, v in sorted(series.items()):
                    lines.append(f"{name}{self._fmt_labels(k)} {v}")
            for name, series in sorted(self._gauges.items()):
                lines.append(f"# HELP {name} {HELP.get(name, name)}")
                lines.append(f"# TYPE {name} gauge")
                for k, v in sorted(series.items()):
                    lines.append(f"{name}{self._fmt_labels(k)} {v}")
            for name, series in sorted(self._hists.items()):
                lines.append(f"# HELP {name} {HELP.get(name, name)}")
                lines.append(f"# TYPE {name} histogram")
                for k, h in sorted(series.items()):
                    for edge, cum in zip(h.buckets, h.cumulative()):
                        lines.append(f"{name}_bucket{self._fmt_labels(k, (('le', str(edge)),))} {cum}")
                    lines.append(f"{name}_bucket{self._fmt_labels(k, (('le', '+Inf'),))} {h.count}")
                    lines.append(f"{name}_sum{self._fmt_labels(k)} {h.sum}")
                    lines.append(f"{name}_count{self._fmt_labels(k)} {h.count}")
        lines.append(f"# TYPE bedtime_uptime_seconds gauge")
        lines.append(f"bedtime_uptime_seconds {round(time.time() - self.started_at, 1)}")
        return "\n".join(lines) + "\n"


METRICS = MetricsRegistry()
