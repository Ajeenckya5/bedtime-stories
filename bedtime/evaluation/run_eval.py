"""End-to-end quality evaluation.

    python -m bedtime.evaluation.run_eval
    python -m bedtime.evaluation.run_eval --mock --repeats 2
Writes reports/EVALUATION_REPORT.md.

Generates a story for every request in QUALITY_SUITE and reports what actually
came out: pass rate, score distribution, revision behaviour, latency, cost, and
whether the requested names survived the pipeline.
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

from ..config import MODEL, get_settings
from ..observability.metrics import METRICS
from ..observability.tracing import LOG
from ..orchestrator import StoryOrchestrator
from ..prompts import PROMPT_VERSION
from ..schemas import RUBRIC_DIMENSIONS, RunStatus
from .metrics_math import describe
from .request_suite import QUALITY_SUITE


def run_suite(repeats: int = 1):
    settings = get_settings()
    orchestrator = StoryOrchestrator(settings=settings)
    rows: List[Dict[str, Any]] = []

    for case in QUALITY_SUITE:
        for attempt in range(max(1, repeats)):
            started = time.perf_counter()
            result = orchestrator.tell(case["request"])
            elapsed = time.perf_counter() - started
            a = result.assessment
            d = a.deterministic if a else None
            story_low = (result.story or "").lower()
            missing = [n for n in case.get("expect", []) if n.lower() not in story_low]

            rows.append({
                "id": case["id"],
                "attempt": attempt,
                "request": case["request"],
                "note": case.get("note", ""),
                "status": result.status.value,
                "category": result.brief.category.value if result.brief else "?",
                "title": result.title,
                "composite": round(a.composite, 2) if a else None,
                "llm_score": round(a.llm_score, 2) if a else None,
                "deterministic_score": round(a.deterministic_score, 2) if a else None,
                "agreement": round(a.agreement, 3) if a else None,
                "passed_gate": bool(a and a.passed),
                "dimensions": a.dimension_medians if a else {},
                "fail_reasons": a.fail_reasons[:3] if a else [],
                "revisions": result.revisions_used,
                "words": d.word_count if d else 0,
                "fk_grade": d.fk_grade if d else 0,
                "human_voice": d.human_voice_score if d else 0,
                "ai_tells": d.ai_tells[:3] if d else [],
                "scary": d.scary_intensity if d else 0,
                "ends_calmly": d.ends_calmly if d else False,
                "missing_names": missing,
                "latency_s": round(elapsed, 2),
                "usd": round(result.usage.usd, 5),
                "calls": result.usage.calls,
                "by_stage": result.usage.by_stage,
                "story": result.story,
            })
            LOG.info("%-5s %-22s %s score=%s rev=%d %.1fs $%.4f",
                     case["id"], (result.title or "")[:22], result.status.value,
                     f"{a.composite:.1f}" if a else "-", result.revisions_used,
                     elapsed, result.usage.usd)
    return rows


def analyse(rows: List[Dict[str, Any]]):
    scored = [r for r in rows if r["composite"] is not None]
    composites = [r["composite"] for r in scored]

    stage_tokens: Dict[str, int] = {}
    for r in rows:
        for stage, tokens in (r.get("by_stage") or {}).items():
            stage_tokens[stage] = stage_tokens.get(stage, 0) + tokens

    by_dimension = {
        dim: describe([r["dimensions"].get(dim, 0) for r in scored if r["dimensions"]])
        for dim in RUBRIC_DIMENSIONS
    }
    by_category: Dict[str, List[float]] = {}
    for r in scored:
        by_category.setdefault(r["category"], []).append(r["composite"])

    return {
        "n": len(rows),
        "scores": describe(composites),
        "latency": describe([r["latency_s"] for r in rows]),
        "cost": describe([r["usd"] for r in rows]),
        "calls": describe([float(r["calls"]) for r in rows]),
        "revisions": describe([float(r["revisions"]) for r in rows]),
        "words": describe([float(r["words"]) for r in scored]),
        "fk": describe([r["fk_grade"] for r in scored]),
        "human_voice": describe([r["human_voice"] for r in scored]),
        "agreement": describe([r["agreement"] for r in scored if r["agreement"]]),
        "pass_rate": round(sum(1 for r in rows if r["passed_gate"]) / max(1, len(rows)), 4),
        "clean_rate": round(sum(1 for r in rows if r["status"] == "ok") / max(1, len(rows)), 4),
        "fallback_rate": round(
            sum(1 for r in rows if r["status"] in {"fallback", "error"}) / max(1, len(rows)), 4),
        "name_retention": round(
            sum(1 for r in rows if not r["missing_names"]) / max(1, len(rows)), 4),
        "calm_rate": round(sum(1 for r in scored if r["ends_calmly"]) / max(1, len(scored)), 4),
        "by_dimension": by_dimension,
        "by_category": {k: describe(v) for k, v in by_category.items()},
        "stage_tokens": stage_tokens,
        "zero_revision_rate": round(
            sum(1 for r in rows if r["revisions"] == 0 and r["passed_gate"]) / max(1, len(rows)), 4),
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

def _banner(settings):
    return MOCK_BANNER if settings.provider == "mock" else ""


def render_report(rows: List[Dict[str, Any]], analysis: Dict[str, Any], settings,
                  elapsed: float, repeats: int) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    s, lat, cost = analysis["scores"], analysis["latency"], analysis["cost"]

    result_rows = "\n".join(
        f"| `{r['id']}` | {r['category']} | {r['status']} | "
        f"{r['composite'] if r['composite'] is not None else '-'} | {r['revisions']} | "
        f"{r['words']} | {r['fk_grade']} | {r['human_voice']:.0f} | "
        f"{'yes' if r['ends_calmly'] else 'NO'} | "
        f"{'-' if not r['missing_names'] else '**' + ','.join(r['missing_names']) + '**'} | "
        f"{r['latency_s']}s | ${r['usd']:.4f} |"
        for r in rows
    )

    dim_rows = "\n".join(
        f"| {dim.replace('_', ' ')} | {RUBRIC_DIMENSIONS[dim]:.2f} | {d['mean']:.2f} | "
        f"{d['sd']:.2f} | {d['min']:.1f} | {d['max']:.1f} |"
        for dim, d in sorted(analysis["by_dimension"].items(),
                             key=lambda kv: kv[1]["mean"])
    )

    cat_rows = "\n".join(
        f"| {cat} | {d['n']} | {d['mean']:.1f} | {d['min']:.1f} | {d['max']:.1f} |"
        for cat, d in sorted(analysis["by_category"].items(), key=lambda kv: kv[1]["mean"])
    )

    total_tokens = sum(analysis["stage_tokens"].values()) or 1
    stage_rows = "\n".join(
        f"| {stage} | {tokens:,} | {tokens / total_tokens:.0%} |"
        for stage, tokens in sorted(analysis["stage_tokens"].items(), key=lambda kv: -kv[1])
    )

    weakest = min(analysis["by_dimension"].items(), key=lambda kv: kv[1]["mean"])
    problems = [r for r in rows if not r["passed_gate"] or r["missing_names"] or not r["ends_calmly"]]
    problem_block = "\n".join(
        f"- `{r['id']}` ({r['status']}, {r['composite']}): "
        + "; ".join(r["fail_reasons"] or (["missing " + ",".join(r["missing_names"])]
                                          if r["missing_names"] else ["ending not calm"]))
        for r in problems[:12]
    ) or "- None. Every request passed the gate on this run."

    sample = next((r for r in rows if r["passed_gate"] and r["story"]), rows[0] if rows else None)
    sample_block = ""
    if sample:
        sample_block = (
            f"### Sample output — `{sample['id']}`\n\n"
            f"> **Request:** {sample['request']}\n\n"
            f"**{sample['title']}** · composite {sample['composite']} · "
            f"{sample['words']} words · FK {sample['fk_grade']} · "
            f"human-voice {sample['human_voice']:.0f}/100\n\n"
            "```\n" + (sample["story"] or "")[:1600] + "\n```\n"
        )

    return _banner(settings) + f"""# End-to-End Evaluation Report

Generated {now} · model `{MODEL}` · prompts `{PROMPT_VERSION}` · provider `{settings.provider}`
{analysis['n']} runs ({len(QUALITY_SUITE)} requests × {repeats}) in {elapsed:.0f}s.

Threshold {settings.gate.accept_threshold:.0f} · {settings.gate.judge_samples} judge samples ·
max {settings.gate.max_revisions} revisions.

## Headline

| | |
|---|---|
| Gate pass rate | **{analysis['pass_rate']:.0%}** |
| Shipped clean (status `ok`) | {analysis['clean_rate']:.0%} |
| Passed with zero revisions | {analysis['zero_revision_rate']:.0%} |
| Fell back to the canned story | {analysis['fallback_rate']:.0%} |
| Requested names present in output | {analysis['name_retention']:.0%} |
| Ends calmly | {analysis['calm_rate']:.0%} |
| Mean composite | {s['mean']:.1f} (sd {s['sd']:.1f}, range {s['min']:.0f}–{s['max']:.0f}) |
| Mean judge agreement | {analysis['agreement']['mean']:.0%} |
| Mean human-voice score | {analysis['human_voice']['mean']:.0f}/100 |

## Cost and latency

| | mean | sd | min | max |
|---|---|---|---|---|
| Latency (s) | {lat['mean']:.1f} | {lat['sd']:.1f} | {lat['min']:.1f} | {lat['max']:.1f} |
| Cost (USD) | {cost['mean']:.4f} | {cost['sd']:.4f} | {cost['min']:.4f} | {cost['max']:.4f} |
| Model calls | {analysis['calls']['mean']:.1f} | {analysis['calls']['sd']:.1f} | {analysis['calls']['min']:.0f} | {analysis['calls']['max']:.0f} |
| Revisions | {analysis['revisions']['mean']:.2f} | {analysis['revisions']['sd']:.2f} | {analysis['revisions']['min']:.0f} | {analysis['revisions']['max']:.0f} |
| Words | {analysis['words']['mean']:.0f} | {analysis['words']['sd']:.0f} | {analysis['words']['min']:.0f} | {analysis['words']['max']:.0f} |
| FK grade | {analysis['fk']['mean']:.1f} | {analysis['fk']['sd']:.1f} | {analysis['fk']['min']:.1f} | {analysis['fk']['max']:.1f} |

Extrapolated: **${cost['mean'] * 1000:.2f} per 1,000 stories**.

### Where the tokens go

| Stage | Tokens | Share |
|---|---|---|
{stage_rows}

If the judge is more than about half the token spend, drop `judge_samples` to 2
and put the saving into an extra revision cycle — revisions move the score, extra
judge samples only measure it more precisely.

## Score by rubric dimension

| Dimension | Weight | Mean | SD | Min | Max |
|---|---|---|---|---|---|
{dim_rows}

Weakest dimension: **{weakest[0].replace('_', ' ')}** ({weakest[1]['mean']:.2f}/5). That is
where the next prompt iteration should go.

## Score by category

| Category | n | Mean | Min | Max |
|---|---|---|---|---|
{cat_rows}

A large spread between categories means one global accept threshold is quietly
stricter on some kinds of request than others.

## Anything that went wrong

{problem_block}

## Every run

| id | category | status | score | rev | words | FK | voice | calm | missing | latency | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
{result_rows}

{sample_block}
## Reproduce

```bash
python -m bedtime.evaluation.run_eval --repeats 2
```
"""

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="End-to-end story quality evaluation.")
    parser.add_argument("--repeats", type=int, default=1)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--out", default="reports/EVALUATION_REPORT.md")
    parser.add_argument("--json-out", default="reports/evaluation_raw.json")
    args = parser.parse_args(argv)

    if args.mock:
        os.environ["BEDTIME_PROVIDER"] = "mock"
    settings = get_settings(refresh=True)

    started = time.perf_counter()
    rows = run_suite(args.repeats)
    analysis = analyse(rows)
    elapsed = time.perf_counter() - started

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_report(rows, analysis, settings, elapsed, args.repeats), encoding="utf-8")
    Path(args.json_out).write_text(
        json.dumps({"rows": rows, "analysis": analysis, "metrics": METRICS.snapshot()},
                   indent=2, default=str), encoding="utf-8")

    print(f"\npass rate {analysis['pass_rate']:.0%} · mean score {analysis['scores']['mean']:.1f} "
          f"· ${analysis['cost']['mean']:.4f}/story · {analysis['latency']['mean']:.1f}s")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
