"""Small stats helpers. Pure stdlib so the eval suite runs anywhere."""

import math
from typing import Dict, List, Sequence, Tuple


def _ranks(values: Sequence[float]) -> List[float]:
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        average = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = average
        i = j + 1
    return ranks


def pearson(x: Sequence[float], y: Sequence[float]) -> float:
    n = len(x)
    if n < 2:
        return 0.0
    mx, my = sum(x) / n, sum(y) / n
    num = sum((a - mx) * (b - my) for a, b in zip(x, y))
    dx = math.sqrt(sum((a - mx) ** 2 for a in x))
    dy = math.sqrt(sum((b - my) ** 2 for b in y))
    return round(num / (dx * dy), 4) if dx and dy else 0.0


def spearman(x: Sequence[float], y: Sequence[float]) -> float:
    return pearson(_ranks(x), _ranks(y))


def kendall_tau(x: Sequence[float], y: Sequence[float]):
    n = len(x)
    if n < 2:
        return 0.0
    concordant = discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            dx, dy = x[i] - x[j], y[i] - y[j]
            product = dx * dy
            if product > 0:
                concordant += 1
            elif product < 0:
                discordant += 1
    total = concordant + discordant
    return round((concordant - discordant) / total, 4) if total else 0.0


def mae(x: Sequence[float], y: Sequence[float]):
    return round(sum(abs(a - b) for a, b in zip(x, y)) / len(x), 4) if x else 0.0


def rmse(x: Sequence[float], y: Sequence[float]) -> float:
    return round(math.sqrt(sum((a - b) ** 2 for a, b in zip(x, y)) / len(x)), 4) if x else 0.0


def confusion(truth: Sequence[bool], predicted: Sequence[bool]) -> Dict[str, int]:
    tp = sum(1 for t, p in zip(truth, predicted) if t and p)
    tn = sum(1 for t, p in zip(truth, predicted) if not t and not p)
    fp = sum(1 for t, p in zip(truth, predicted) if not t and p)
    fn = sum(1 for t, p in zip(truth, predicted) if t and not p)
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def prf(truth: Sequence[bool], predicted: Sequence[bool]) -> Dict[str, float]:
    c = confusion(truth, predicted)
    precision = c["tp"] / (c["tp"] + c["fp"]) if (c["tp"] + c["fp"]) else 0.0
    recall = c["tp"] / (c["tp"] + c["fn"]) if (c["tp"] + c["fn"]) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    total = sum(c.values()) or 1
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round((c["tp"] + c["tn"]) / total, 4),
        **c,
    }


def threshold_sweep(scores: Sequence[float], truth: Sequence[bool],
                    lo: float = 50.0, hi: float = 95.0,
                    step: float = 1.0) -> List[Tuple[float, Dict[str, float]]]:
    out = []
    t = lo
    while t <= hi + 1e-9:
        predicted = [s >= t for s in scores]
        out.append((round(t, 2), prf(truth, predicted)))
        t += step
    return out


def best_threshold(sweep: List[Tuple[float, Dict[str, float]]],
                   min_precision: float = 0.85) -> Tuple[float, Dict[str, float]]:
    """Pick the highest-F1 threshold that still meets a precision floor."""
    eligible = [(t, m) for t, m in sweep if m["precision"] >= min_precision]
    pool = eligible or sweep
    return max(pool, key=lambda tm: (tm[1]["f1"], tm[1]["precision"]))


def describe(values: Sequence[float]):
    if not values:
        return {"n": 0, "mean": 0.0, "sd": 0.0, "min": 0.0, "max": 0.0, "p50": 0.0}
    ordered = sorted(values)
    n = len(ordered)
    mean = sum(ordered) / n
    sd = math.sqrt(sum((v - mean) ** 2 for v in ordered) / n)
    return {
        "n": n,
        "mean": round(mean, 3),
        "sd": round(sd, 3),
        "min": round(ordered[0], 3),
        "max": round(ordered[-1], 3),
        "p50": round(ordered[n // 2], 3),
    }
