"""Judge calibration.

    python -m bedtime.evaluation.calibrate                  # uses your key
    python -m bedtime.evaluation.calibrate --mock           # offline smoke test
    python -m bedtime.evaluation.calibrate --samples 5

Runs the judge over the hand-labelled golden set and answers three questions:
  1. Does the judge rank stories the way a human does?   (Spearman / Kendall)
  2. Where should the accept threshold sit?              (sweep + F1)
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..agents.judge import Judge
from ..config import MODEL, get_settings
from ..guardrails.readability import readability_report
from ..observability.tracing import LOG, RunTrace
from ..orchestrator import build_provider
from ..prompts import PROMPT_VERSION
from ..schemas import RUBRIC_DIMENSIONS, StoryBrief
from .golden_set import GOLDEN_SET, summary
from .metrics_math import (
    best_threshold,
    describe,
    kendall_tau,
    mae,
    pearson,
    prf,
    rmse,
    spearman,
    threshold_sweep,
)


def score_golden_set(samples: int, repeats: int = 1) -> List[Dict[str, Any]]:
    settings = get_settings()
    provider = build_provider(settings)
    rows: List[Dict[str, Any]] = []

    for entry in GOLDEN_SET:
        trace = RunTrace(trace_dir=settings.trace_dir,
                         metadata={"kind": "calibration", "golden_id": entry["id"]})
        brief = StoryBrief(raw_request=entry["request"], sanitized_request=entry["request"])
        det = readability_report(entry["story"], settings.age_band)
        judge = Judge(provider, settings, trace)

        composites, llm_scores, agreements, safety_flags = [], [], [], []
        per_dimension: Dict[str, List[float]] = {d: [] for d in RUBRIC_DIMENSIONS}

        for _ in range(max(1, repeats)):
            started = time.perf_counter()
            assessment = judge.assess(entry["story"], brief, det, samples=samples)
            composites.append(assessment.composite)
            llm_scores.append(assessment.llm_score)
            agreements.append(assessment.agreement)
            safety_flags.append(assessment.safety_violation)
            for dim, value in assessment.dimension_medians.items():
                per_dimension.setdefault(dim, []).append(value)
            LOG.info("%-18s human=%d judge=%.1f agree=%.2f (%.1fs)",
                     entry["id"], entry["human_score"], assessment.composite,
                     assessment.agreement, time.perf_counter() - started)

        rows.append({
            "id": entry["id"],
            "request": entry["request"],
            "human_score": entry["human_score"],
            "human_should_ship": entry["human_score"] >= 4,
            "human_unsafe": entry["unsafe"],
            "note": entry["note"],
            "judge_composite": round(statistics.mean(composites), 2),
            "judge_composite_runs": composites,
            "judge_llm_score": round(statistics.mean(llm_scores), 2),
            "deterministic": round(0.6 * det.readability_score + 0.4 * det.human_voice_score, 2),
            "readability_score": det.readability_score,
            "human_voice_score": det.human_voice_score,
            "fk_grade": det.fk_grade,
            "agreement": round(statistics.mean(agreements), 3),
            "judge_flagged_unsafe": any(safety_flags),
            "deterministic_blocked": bool(det.banned_terms) or not det.passed,
            "dimensions": {d: round(statistics.mean(v), 2) for d, v in per_dimension.items() if v},
            "stability": round(max(composites) - min(composites), 2) if len(composites) > 1 else 0.0,
        })
    return rows


def analyse(rows: List[Dict[str, Any]], settings):
    human = [r["human_score"] for r in rows]
    judge = [r["judge_composite"] for r in rows]
    llm_only = [r["judge_llm_score"] for r in rows]
    det_only = [r["deterministic"] for r in rows]

    # Human 1-5 projected onto the same 0-100 scale so MAE is interpretable.
    human_100 = [(h - 1) / 4 * 100 for h in human]
    should_ship = [r["human_should_ship"] for r in rows]

    sweep = threshold_sweep(judge, should_ship, lo=50, hi=95, step=1.0)
    chosen, chosen_metrics = best_threshold(sweep, min_precision=0.85)

    unsafe_truth = [r["human_unsafe"] for r in rows]
    unsafe_pred_judge = [r["judge_flagged_unsafe"] for r in rows]
    unsafe_pred_any = [r["judge_flagged_unsafe"] or r["deterministic_blocked"] for r in rows]

    return {
        "correlation": {
            "spearman_blended": spearman(human, judge),
            "spearman_llm_only": spearman(human, llm_only),
            "spearman_deterministic_only": spearman(human, det_only),
            "pearson_blended": pearson(human, judge),
            "kendall_tau_blended": kendall_tau(human, judge),
            "mae_vs_human_100": mae(human_100, judge),
            "rmse_vs_human_100": rmse(human_100, judge),
        },
        "threshold": {
            "current": settings.gate.accept_threshold,
            "recommended": chosen,
            "recommended_metrics": chosen_metrics,
            "current_metrics": prf(should_ship, [s >= settings.gate.accept_threshold for s in judge]),
            "sweep": sweep,
        },
        "safety": {
            "judge_only": prf(unsafe_truth, unsafe_pred_judge),
            "judge_plus_deterministic": prf(unsafe_truth, unsafe_pred_any),
        },
        "agreement": describe([r["agreement"] for r in rows]),
        "stability": describe([r["stability"] for r in rows]),
        "by_dimension": {
            dim: round(spearman(human, [r["dimensions"].get(dim, 3.0) for r in rows]), 4)
            for dim in RUBRIC_DIMENSIONS
        },
    }


MOCK_BANNER = """> ### These numbers are placeholders
>
> This report was generated with `--mock`, the offline provider. The mock judge is
> a deterministic proxy, not a language model, so **every correlation, threshold
> and score below is meaningless as evidence**. It proves the harness runs
> end-to-end; it proves nothing about story quality.
>
> Re-run with an `OPENAI_API_KEY` set to get real numbers:
> ```bash
> python -m bedtime.evaluation.calibrate
> python -m bedtime.evaluation.run_eval
> python -m bedtime.evaluation.red_team
> ```

"""

def _banner(settings) -> str:
    return MOCK_BANNER if settings.provider == "mock" else ""


def render_report(rows: List[Dict[str, Any]], analysis: Dict[str, Any],
                  settings, samples: int, repeats: int, elapsed: float) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    c = analysis["correlation"]
    t = analysis["threshold"]
    s = analysis["safety"]
    counts = summary()

    def verdict(value: float, good: float, ok: float):
        return "good" if value >= good else ("acceptable" if value >= ok else "**weak**")

    detail_rows = "\n".join(
        f"| `{r['id']}` | {r['human_score']} | {'yes' if r['human_should_ship'] else 'no'} | "
        f"{r['judge_composite']:.1f} | {r['judge_llm_score']:.1f} | {r['deterministic']:.1f} | "
        f"{r['human_voice_score']:.0f} | {r['agreement']:.2f} | "
        f"{'FLAG' if r['judge_flagged_unsafe'] else '-'} | {r['note']} |"
        for r in sorted(rows, key=lambda r: -r["human_score"])
    )

    sweep_rows = "\n".join(
        f"| {th:.0f} | {m['precision']:.2f} | {m['recall']:.2f} | {m['f1']:.2f} | "
        f"{m['tp']}/{m['fp']}/{m['fn']}/{m['tn']} |"
        for th, m in t["sweep"] if 60 <= th <= 92 and int(th) % 2 == 0
    )

    dim_rows = "\n".join(
        f"| {dim.replace('_', ' ')} | {weight:.2f} | {analysis['by_dimension'].get(dim, 0):+.2f} |"
        for dim, weight in sorted(RUBRIC_DIMENSIONS.items(), key=lambda kv: -kv[1])
    )

    disagreements = [
        r for r in rows
        if (r["judge_composite"] >= t["recommended"]) != r["human_should_ship"]
    ]
    disagree_block = "\n".join(
        f"- `{r['id']}` — human {r['human_score']}/5 "
        f"({'ship' if r['human_should_ship'] else 'block'}), judge {r['judge_composite']:.1f} "
        f"({'ship' if r['judge_composite'] >= t['recommended'] else 'block'}). {r['note']}"
        for r in disagreements
    ) or "- None. The judge and I agreed on every story at the recommended threshold."

    return _banner(settings) + f"""# Judge Calibration Report

Generated {now} · model `{MODEL}` · prompts `{PROMPT_VERSION}` · provider `{settings.provider}`
{samples} judge samples per assessment, {repeats} repeat(s) per story, {elapsed:.0f}s total.

## What this measures

An LLM judge is only useful if its scores track something real. This runs the
judge over {counts['total']} hand-labelled stories ({counts['should_ship']} I would ship,
{counts['unsafe']} that must be blocked) and checks three things: does it rank
stories the way I do, where should the gate sit, and how much does a single
sample wobble.

## 1. Does the judge agree with the human labels?

| Metric | Value | Reading |
|---|---|---|
| Spearman ρ (blended score) | **{c['spearman_blended']:+.3f}** | {verdict(abs(c['spearman_blended']), 0.75, 0.55)} |
| Spearman ρ (LLM rubric only) | {c['spearman_llm_only']:+.3f} | rubric on its own |
| Spearman ρ (deterministic only) | {c['spearman_deterministic_only']:+.3f} | readability + human-voice on their own |
| Kendall τ | {c['kendall_tau_blended']:+.3f} | pairwise ordering |
| Pearson r | {c['pearson_blended']:+.3f} | linear fit |
| MAE vs human (0-100 scale) | {c['mae_vs_human_100']:.1f} pts | absolute error |
| RMSE | {c['rmse_vs_human_100']:.1f} pts | penalises large misses |

The comparison that matters is the first three rows. If the blended score does not
beat both components individually, the 75/25 weighting in `QualityGate` is wrong
and should be re-tuned.

## 2. Where should the threshold sit?

Current: **{t['current']:.0f}** · Recommended: **{t['recommended']:.0f}**

At the recommended threshold: precision {t['recommended_metrics']['precision']:.2f},
recall {t['recommended_metrics']['recall']:.2f}, F1 {t['recommended_metrics']['f1']:.2f},
accuracy {t['recommended_metrics']['accuracy']:.2f}.

At the currently configured threshold: precision {t['current_metrics']['precision']:.2f},
recall {t['current_metrics']['recall']:.2f}, F1 {t['current_metrics']['f1']:.2f}.

| Threshold | Precision | Recall | F1 | TP/FP/FN/TN |
|---|---|---|---|---|
{sweep_rows}

Threshold selection favours precision (floor 0.85). Shipping a weak story to a
child costs more than spending one extra revision cycle, and revisions are
cheap — roughly $0.002 each.

Set it with `BEDTIME_ACCEPT_THRESHOLD={t['recommended']:.0f}`.

## 3. How noisy is the judge?

| | mean | sd | min | max |
|---|---|---|---|---|
| Inter-sample agreement | {analysis['agreement']['mean']:.3f} | {analysis['agreement']['sd']:.3f} | {analysis['agreement']['min']:.3f} | {analysis['agreement']['max']:.3f} |
| Run-to-run score spread | {analysis['stability']['mean']:.2f} | {analysis['stability']['sd']:.2f} | {analysis['stability']['min']:.2f} | {analysis['stability']['max']:.2f} |

Agreement is `1 - mean(dimension spread) / 4`. Anything under ~0.75 means the
judge is guessing on that story, which is why `min_improvement_delta` exists:
a revision that gains less than {settings.gate.min_improvement_delta} points is
inside the noise floor and does not count as progress.

## 4. Safety detection

| Detector | Precision | Recall | F1 | FN |
|---|---|---|---|---|
| Judge flag alone | {s['judge_only']['precision']:.2f} | {s['judge_only']['recall']:.2f} | {s['judge_only']['f1']:.2f} | {s['judge_only']['fn']} |
| Judge + deterministic | {s['judge_plus_deterministic']['precision']:.2f} | {s['judge_plus_deterministic']['recall']:.2f} | {s['judge_plus_deterministic']['f1']:.2f} | {s['judge_plus_deterministic']['fn']} |

False negatives are the only number that really matters here. The layered
detector should reach 0; if it does not, the gap goes straight into the lexicon
in `guardrails/lexicons.py`.

## 5. Per-dimension correlation with the human label

| Dimension | Weight | Spearman ρ |
|---|---|---|
{dim_rows}

A dimension with near-zero correlation is either badly anchored in the prompt or
measuring something the human label doesn't capture. Either way it should not be
carrying weight in the composite.

## 6. Where the judge and I disagreed

{disagree_block}

## Full results

| id | human | ship? | composite | LLM | determ. | voice | agree | safety | note |
|---|---|---|---|---|---|---|---|---|---|
{detail_rows}

## How to re-run

```bash
python -m bedtime.evaluation.calibrate --samples 3 --repeats 2
```

Re-run after any change to `bedtime/prompts.py` (bump `PROMPT_VERSION` first),
after changing the rubric weights in `schemas.py`, or after an OpenAI model
snapshot update. Those are the three things that move these numbers.
"""

def main(argv=None):
    parser = argparse.ArgumentParser(description="Calibrate the LLM judge against the golden set.")
    parser.add_argument("--samples", type=int, default=3, help="judge samples per assessment")
    parser.add_argument("--repeats", type=int, default=1, help="repeat each story to measure stability")
    parser.add_argument("--mock", action="store_true", help="offline provider (smoke test only)")
    parser.add_argument("--out", default="reports/CALIBRATION_REPORT.md")
    parser.add_argument("--json-out", default="reports/calibration_raw.json")
    args = parser.parse_args(argv)

    if args.mock:
        os.environ["BEDTIME_PROVIDER"] = "mock"
    settings = get_settings(refresh=True)

    started = time.perf_counter()
    rows = score_golden_set(args.samples, args.repeats)
    analysis = analyse(rows, settings)
    elapsed = time.perf_counter() - started

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(rows, analysis, settings, args.samples, args.repeats, elapsed),
                   encoding="utf-8")
    Path(args.json_out).write_text(
        json.dumps({"rows": rows, "analysis": analysis}, indent=2, default=str), encoding="utf-8")

    c = analysis["correlation"]
    print(f"\nSpearman ρ = {c['spearman_blended']:+.3f} (llm-only {c['spearman_llm_only']:+.3f}, "
          f"deterministic-only {c['spearman_deterministic_only']:+.3f})")
    print(f"recommended threshold = {analysis['threshold']['recommended']:.0f} "
          f"(F1 {analysis['threshold']['recommended_metrics']['f1']:.2f})")
    print(f"unsafe false negatives = {analysis['safety']['judge_plus_deterministic']['fn']}")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
