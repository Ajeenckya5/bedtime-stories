"""Self-contained HTML dashboard built from the JSONL traces.

No JS framework, no CDN, no build step - it has to open from a file:// URL on a
laptop with no network. Charts are inline SVG.

    python -m bedtime.observability.dashboard          # writes reports/dashboard.html
    GET /dashboard                                     # same thing, live
"""

from __future__ import annotations

import html
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from .tracing import read_traces

CSS = """
:root{--bg:#0e1116;--panel:#161b22;--line:#232a35;--txt:#e6edf3;--dim:#8b949e;
--ok:#3fb950;--warn:#d29922;--bad:#f85149;--acc:#58a6ff}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font:14px/1.5 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif}
header{padding:24px 32px;border-bottom:1px solid var(--line)}
h1{margin:0;font-size:19px;letter-spacing:.2px}
.sub{color:var(--dim);font-size:12px;margin-top:6px}
main{padding:24px 32px;max-width:1280px}
.grid{display:grid;gap:14px;grid-template-columns:repeat(auto-fit,minmax(178px,1fr));margin-bottom:26px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:16px}
.card .k{color:var(--dim);font-size:11px;text-transform:uppercase;letter-spacing:.6px}
.card .v{font-size:26px;font-weight:600;margin-top:6px}
.card .n{color:var(--dim);font-size:11px;margin-top:4px}
.ok{color:var(--ok)}.warn{color:var(--warn)}.bad{color:var(--bad)}.acc{color:var(--acc)}
section{background:var(--panel);border:1px solid var(--line);border-radius:8px;
padding:18px;margin-bottom:20px}
section h2{margin:0 0 14px;font-size:13px;text-transform:uppercase;
letter-spacing:.7px;color:var(--dim)}
table{width:100%;border-collapse:collapse;font-size:13px}
th{text-align:left;color:var(--dim);font-weight:500;font-size:11px;
text-transform:uppercase;letter-spacing:.5px;padding:6px 10px;border-bottom:1px solid var(--line)}
td{padding:7px 10px;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:none}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.bar{height:7px;background:#21262d;border-radius:4px;overflow:hidden;min-width:70px}
.bar>i{display:block;height:100%;border-radius:4px}
.pill{display:inline-block;padding:1px 8px;border-radius:11px;font-size:11px;
border:1px solid var(--line)}
.empty{color:var(--dim);padding:22px 0;text-align:center}
footer{color:var(--dim);font-size:11px;padding:0 32px 32px}
"""

def _pct_class(value: float, good: float, warn: float):
    return "ok" if value >= good else ("warn" if value >= warn else "bad")


def _bar(value: float, maximum: float, colour: str):
    width = 0 if maximum <= 0 else max(2, min(100, value / maximum * 100))
    return f'<div class="bar"><i style="width:{width:.1f}%;background:{colour}"></i></div>'


def _sparkline(values: List[float], width: int = 620, height: int = 90,
               threshold: Optional[float] = None) -> str:
    if len(values) < 2:
        return '<div class="empty">not enough runs yet</div>'
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1.0
    pad = 6
    step = (width - 2 * pad) / (len(values) - 1)
    pts = " ".join(
        f"{pad + i * step:.1f},{height - pad - (v - lo) / span * (height - 2 * pad):.1f}"
        for i, v in enumerate(values)
    )
    line = ""
    if threshold is not None and lo <= threshold <= hi:
        y = height - pad - (threshold - lo) / span * (height - 2 * pad)
        line = (f'<line x1="{pad}" y1="{y:.1f}" x2="{width - pad}" y2="{y:.1f}" '
                f'stroke="#d29922" stroke-dasharray="4 4" stroke-width="1"/>')
    return (
        f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}">'
        f'{line}<polyline points="{pts}" fill="none" stroke="#58a6ff" stroke-width="2" '
        f'stroke-linejoin="round"/></svg>'
        f'<div class="sub">oldest -> newest &nbsp;·&nbsp; min {lo:.1f} &nbsp; max {hi:.1f}'
        + (f' &nbsp;·&nbsp; dashed line = accept threshold {threshold:.0f}' if threshold else '')
        + '</div>'
    )


def _histogram(values: List[float], buckets: int = 10):
    if not values:
        return '<div class="empty">no data</div>'
    lo, hi = min(values), max(values)
    if hi - lo < 1e-9:
        hi = lo + 1
    width = (hi - lo) / buckets
    counts = [0] * buckets
    for v in values:
        idx = min(buckets - 1, int((v - lo) / width))
        counts[idx] += 1
    peak = max(counts) or 1
    rows = "".join(
        f"<tr><td class='mono'>{lo + i * width:.0f}–{lo + (i + 1) * width:.0f}</td>"
        f"<td style='width:60%'>{_bar(c, peak, '#58a6ff')}</td>"
        f"<td class='mono'>{c}</td></tr>"
        for i, c in enumerate(counts)
    )
    return f"<table>{rows}</table>"


def collect(trace_dir: Path, limit: int = 2000):
    rows = read_traces(trace_dir, limit=limit)
    runs = [r for r in rows if r.get("result")]
    runs.sort(key=lambda r: r.get("ts", 0))

    composites = [r["result"]["composite"] for r in runs
                  if isinstance(r["result"].get("composite"), (int, float))]
    latencies = [r["result"].get("latency_s", 0) for r in runs]
    costs = [r["result"].get("usd", 0) or 0 for r in runs]
    revisions = [r["result"].get("revisions", 0) or 0 for r in runs]
    agreements = [r["result"]["agreement"] for r in runs
                  if isinstance(r["result"].get("agreement"), (int, float))]

    statuses: Dict[str, int] = {}
    for r in runs:
        statuses[r["result"].get("status", "?")] = statuses.get(r["result"].get("status", "?"), 0) + 1

    # Guardrail + gate events come out of the span events, not the summary.
    blocks: Dict[str, int] = {}
    stage_time: Dict[str, float] = {}
    for r in rows:
        for span in r.get("spans", []):
            stage_time[span["name"]] = stage_time.get(span["name"], 0.0) + span.get("duration_s", 0)
            for ev in span.get("events", []):
                msg = ev.get("message", "")
                if msg in {"fallback_served", "candidate_vetoed", "regenerating",
                           "revision_stalled", "budget_stop"}:
                    blocks[msg] = blocks.get(msg, 0) + 1
                if msg == "input_screened" and ev.get("decision") in {"refuse", "sanitize"}:
                    key = f"input_{ev['decision']}"
                    blocks[key] = blocks.get(key, 0) + 1

    return {
        "runs": runs,
        "n": len(runs),
        "composites": composites,
        "latencies": latencies,
        "costs": costs,
        "revisions": revisions,
        "agreements": agreements,
        "statuses": statuses,
        "blocks": blocks,
        "stage_time": stage_time,
    }


def render_dashboard(trace_dir: Path, metrics_snapshot: Optional[Dict[str, Any]] = None,
                     settings=None) -> str:
    d = collect(Path(trace_dir))
    n = d["n"]
    threshold = getattr(getattr(settings, "gate", None), "accept_threshold", 82.0)

    if n == 0:
        body = ('<div class="empty">No traces yet. Generate a story, then reload.<br>'
                '<span class="mono">python main.py "a story about a shy dragon"</span></div>')
        return _page(body, "0 runs")

    ok = d["statuses"].get("ok", 0)
    degraded = d["statuses"].get("ok_degraded", 0)
    pass_rate = ok / n * 100
    mean_score = statistics.mean(d["composites"]) if d["composites"] else 0.0
    p95_latency = sorted(d["latencies"])[int(0.95 * (len(d["latencies"]) - 1))] if d["latencies"] else 0
    mean_agreement = statistics.mean(d["agreements"]) if d["agreements"] else 0.0
    total_cost = sum(d["costs"])
    mean_revisions = statistics.mean(d["revisions"]) if d["revisions"] else 0.0

    cards = [
        ("Runs", f"{n}", f"{ok} clean · {degraded} degraded", "acc"),
        ("First-pass rate", f"{pass_rate:.0f}%", "shipped without degradation",
         _pct_class(pass_rate, 80, 60)),
        ("Mean quality", f"{mean_score:.1f}", f"threshold {threshold:.0f}",
         _pct_class(mean_score, threshold, threshold - 12)),
        ("Judge agreement", f"{mean_agreement:.0%}", "1 - normalised sample spread",
         _pct_class(mean_agreement * 100, 80, 65)),
        ("p95 latency", f"{p95_latency:.1f}s", f"mean {statistics.mean(d['latencies']):.1f}s",
         _pct_class(120 - p95_latency, 60, 30)),
        ("Spend", f"${total_cost:.3f}", f"${total_cost / n:.4f} per story", "acc"),
        ("Revisions", f"{mean_revisions:.2f}", "average cycles per story",
         _pct_class(3 - mean_revisions, 2, 1)),
    ]
    cards_html = "".join(
        f'<div class="card"><div class="k">{k}</div>'
        f'<div class="v {cls}">{v}</div><div class="n">{note}</div></div>'
        for k, v, note, cls in cards
    )

    status_rows = "".join(
        f'<tr><td><span class="pill">{html.escape(s)}</span></td>'
        f'<td style="width:60%">{_bar(c, n, "#3fb950" if s == "ok" else "#d29922")}</td>'
        f'<td class="mono">{c} ({c / n:.0%})</td></tr>'
        for s, c in sorted(d["statuses"].items(), key=lambda kv: -kv[1])
    )

    block_rows = "".join(
        f'<tr><td>{html.escape(k.replace("_", " "))}</td>'
        f'<td class="mono">{v}</td></tr>'
        for k, v in sorted(d["blocks"].items(), key=lambda kv: -kv[1])
    ) or '<tr><td class="empty" colspan="2">no guardrail events</td></tr>'

    total_stage = sum(d["stage_time"].values()) or 1
    stage_rows = "".join(
        f'<tr><td>{html.escape(k)}</td>'
        f'<td style="width:50%">{_bar(v, max(d["stage_time"].values()), "#58a6ff")}</td>'
        f'<td class="mono">{v:.1f}s ({v / total_stage:.0%})</td></tr>'
        for k, v in sorted(d["stage_time"].items(), key=lambda kv: -kv[1])[:12]
    )

    recent = d["runs"][-25:][::-1]
    recent_rows = "".join(
        f'<tr><td class="mono">{html.escape(str(r["result"].get("run_id", ""))[:16])}</td>'
        f'<td>{html.escape(str(r["result"].get("title", ""))[:44])}</td>'
        f'<td><span class="pill">{html.escape(str(r["result"].get("status", "")))}</span></td>'
        f'<td class="mono {_pct_class(r["result"].get("composite") or 0, threshold, threshold - 12)}">'
        f'{r["result"].get("composite", "-")}</td>'
        f'<td class="mono">{r["result"].get("agreement", "-")}</td>'
        f'<td class="mono">{r["result"].get("revisions", 0)}</td>'
        f'<td class="mono">{r["result"].get("fk_grade", "-")}</td>'
        f'<td class="mono">{r["result"].get("words", "-")}</td>'
        f'<td class="mono">{r["result"].get("latency_s", "-")}s</td>'
        f'<td class="mono">${r["result"].get("usd", 0):.4f}</td></tr>'
        for r in recent
    )

    body = f"""
<div class="grid">{cards_html}</div>

<section><h2>Quality over time</h2>{_sparkline(d["composites"], threshold=threshold)}</section>

<div style="display:grid;gap:20px;grid-template-columns:repeat(auto-fit,minmax(330px,1fr))">
  <section><h2>Score distribution</h2>{_histogram(d["composites"])}</section>
  <section><h2>Outcomes</h2><table>{status_rows}</table></section>
  <section><h2>Guardrail &amp; loop events</h2><table>{block_rows}</table></section>
  <section><h2>Time by stage</h2><table>{stage_rows}</table></section>
</div>

<section><h2>Recent runs</h2><table>
<tr><th>run</th><th>title</th><th>status</th><th>score</th><th>agree</th>
<th>rev</th><th>FK</th><th>words</th><th>latency</th><th>cost</th></tr>
{recent_rows}</table></section>
"""
    return _page(body, f"{n} runs")


def _page(body: str, subtitle: str) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Bedtime Story Engine — monitoring</title><style>{CSS}</style></head><body>
<header><h1>Bedtime Story Engine</h1>
<div class="sub">{subtitle} · generated {now}</div></header>
<main>{body}</main>
<footer>Built from JSONL traces. Prometheus metrics at <span class="mono">/metrics</span>.</footer>
</body></html>"""

def main(argv=None):
    from ..config import get_settings

    settings = get_settings()
    argv = argv or sys.argv[1:]
    out = Path(argv[0]) if argv else Path("reports/dashboard.html")
    out.parent.mkdir(parents=True, exist_ok=True)
    from .metrics import METRICS

    out.write_text(render_dashboard(settings.trace_dir, METRICS.snapshot(), settings),
                   encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
