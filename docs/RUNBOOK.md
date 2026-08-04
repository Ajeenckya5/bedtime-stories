# Runbook

Deploy, monitor, alert, debug.

## Deploy

```bash
pip install -r requirements.txt
export OPENAI_API_KEY=sk-...
uvicorn bedtime.api:app --host 0.0.0.0 --port 8000 --workers 4
```

Container:

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV BEDTIME_TRACE_DIR=/var/log/bedtime
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://localhost:8000/health')"
CMD ["uvicorn","bedtime.api:app","--host","0.0.0.0","--port","8000","--workers","4"]
```

Notes on scaling: state is per-process (metrics registry, recent-results cache,
rate-limit buckets, circuit breaker). With >1 worker each has its own. That's fine
for metrics if you scrape all of them, but the `/feedback` endpoint needs sticky
sessions or a shared store, and the per-day budget cap becomes per-worker. For
real multi-node, move the ledger and recent-results cache to Redis — both are
small, well-isolated interfaces.

## Endpoints

| Route | Purpose |
|---|---|
| `POST /story` | generate. `{request, include_plan?, include_candidates?}` |
| `POST /feedback` | revise an existing run. `{run_id, feedback}` |
| `GET /health` | liveness — no model call, never rate-limited |
| `GET /ready` | readiness — 503 if the circuit breaker is open |
| `GET /metrics` | Prometheus text exposition |
| `GET /metrics.json` | same data as JSON |
| `GET /dashboard` | HTML monitoring view |
| `GET /config` | redacted settings (auth required) |

Auth is off until you set `BEDTIME_SERVICE_API_KEYS=key1,key2`. Then every route
except `/health`, `/ready`, `/metrics` and `/dashboard` needs `x-api-key`.

## Configuration

Everything is env-driven; see `.env.example`. The ones you'll actually touch:

| Var | Default | Effect |
|---|---|---|
| `BEDTIME_ACCEPT_THRESHOLD` | 82 | quality gate. Raise for stricter, more revisions, higher cost |
| `BEDTIME_JUDGE_SAMPLES` | 3 | 1 = cheap/noisy, 3 = recommended, 5 = research-grade |
| `BEDTIME_MAX_REVISIONS` | 3 | ceiling on revise cycles |
| `BEDTIME_MAX_USD_PER_RUN` | 0.25 | per-run blast radius |
| `BEDTIME_MAX_USD_PER_DAY` | 25.00 | daily cap |
| `BEDTIME_RATE_LIMIT_RPM` | 60 | outbound to OpenAI |
| `BEDTIME_API_RATE_LIMIT_RPM` | 20 | inbound per caller |
| `BEDTIME_STRICT_SAFETY` | true | ambiguous → refuse |
| `BEDTIME_USE_MODERATION_API` | true | set false for a pure-gpt-3.5 system |
| `BEDTIME_VALIDATORS` | *(empty)* | `guardrails_ai`, `nemo`, `lexicon` |
| `BEDTIME_REDACT_TRACES` | false | strip story text from traces |
| `BEDTIME_PROVIDER` | auto | `mock` for offline |

## Monitoring

### Key metrics

| Metric | Watch for |
|---|---|
| `stories_total{status}` | `fallback` or `error` share rising |
| `story_quality_score` | p50 drifting down — usually a model snapshot change |
| `judge_disagreement` | rising means the judge is less certain; check prompt drift |
| `story_latency_seconds` | p95 — user-visible |
| `llm_errors_total{stage}` | upstream trouble, by stage |
| `llm_retries_total` | leading indicator before errors show up |
| `guardrail_blocks_total{guardrail,reason}` | a spike in one reason = attack or a bad deploy |
| `gate_failures_total{reason}` | which quality dimension is failing most |
| `fallback_served_total{reason}` | should be near zero |
| `llm_cost_usd_total{stage}` | judge is usually the largest share |
| `revision_stalled_total` | loop hitting the noise floor a lot → threshold too high |

### Alerts

```yaml
- alert: BedtimeFallbackRate
  expr: rate(fallback_served_total[10m]) / rate(stories_total[10m]) > 0.05
  for: 10m
  annotations: {summary: ">5% of stories are serving the canned fallback"}

- alert: BedtimeQualityDrop
  expr: histogram_quantile(0.5, rate(story_quality_score_bucket[1h])) < 78
  for: 30m
  annotations: {summary: "median quality below 78 — check for a model snapshot change"}

- alert: BedtimeCircuitOpen
  expr: increase(llm_errors_total[5m]) > 20
  for: 5m
  annotations: {summary: "upstream failing; /ready is returning 503"}

- alert: BedtimeCostSpike
  expr: increase(llm_cost_usd_total[1h]) > 5
  annotations: {summary: "hourly spend above $5 — check revision loop behaviour"}

- alert: BedtimeSafetyBlockSpike
  expr: rate(guardrail_blocks_total{guardrail="input"}[15m]) > 0.3
  for: 15m
  annotations: {summary: "unusual rate of blocked requests — possible probing"}

- alert: BedtimeLatency
  expr: histogram_quantile(0.95, rate(story_latency_seconds_bucket[15m])) > 90
  for: 15m
```

### Dashboard

```bash
python -m bedtime.observability.dashboard    # → reports/dashboard.html
```

Or live at `/dashboard`. Shows score trend against threshold, outcome breakdown,
guardrail events, score histogram, time by stage, and the 25 most recent runs.

## Debugging

Traces are JSONL, one line per run, in `$BEDTIME_TRACE_DIR` (default `traces/`).

```bash
# a specific run
jq 'select(.run_id=="run_abc123")' traces/*.jsonl

# everything that fell back, and why
jq 'select(.result.status=="fallback") | {run_id, spans: [.spans[].events[] | select(.message=="fallback_served")]}' traces/*.jsonl

# worst 10 runs
jq -s 'map(select(.result.composite)) | sort_by(.result.composite) | .[0:10] | .[] | {run_id, composite: .result.composite, title: .result.title}' traces/*.jsonl

# where time goes
jq -s '[.[].spans[]] | group_by(.name) | map({stage: .[0].name, total: (map(.duration_s) | add), n: length})' traces/*.jsonl

# runs where the judge disagreed with itself
jq 'select(.result.agreement < 0.7) | {run_id, agreement: .result.agreement, composite: .result.composite}' traces/*.jsonl

# quality by prompt version (after a prompt change)
jq -s 'group_by(.metadata.prompt_version) | map({version: .[0].metadata.prompt_version, n: length, mean: ((map(.result.composite // 0) | add) / length)})' traces/*.jsonl
```

## Playbooks

**Fallback rate spiked.** Check `fallback_served_total{reason}`. `budget` → a
revision loop isn't converging, look at `revision_stalled_total` and consider
lowering the threshold. `all candidates vetoed` → a safety check is over-firing;
find which in `guardrail_blocks_total{reason}`. `ProviderError` → upstream.

**Quality dropped with no deploy.** Almost always an OpenAI model snapshot change.
Re-run `make reports` and compare against the committed reports. If the judge
moved too, re-run calibration and re-derive the threshold.

**Costs climbed.** Check `llm_cost_usd_total{stage}`. If `judge` is >50%, drop
`BEDTIME_JUDGE_SAMPLES` to 2 — you lose some precision in the score but the money
is better spent on an extra revision, which actually moves quality.

**Users say stories are refused too often.** Look at
`guardrail_blocks_total{guardrail="input",reason}`. If `lexicon` dominates, a word
is over-firing — check word boundaries. If `llm_screen` dominates, the screen
prompt has drifted strict; re-run the red-team suite and check the over-refusal
rate on the benign controls.

**Latency spike.** Check `llm_latency_seconds` p95 by stage. If it's `judge`, you're
paying for 3 sequential samples — they're independent and could be parallelised
(known gap; see DESIGN_NOTES).

## CI

```bash
make check     # secret scan + 70 tests + red team with --strict-exit
```

`--strict-exit` fails the build on any successful attack or PII leak. That should
be a required check.

Re-run `make reports` after: any change to `bedtime/prompts.py` (bump
`PROMPT_VERSION` first), any change to rubric weights in `schemas.py`, or any
OpenAI model update. Commit the regenerated reports — the diff is the evidence.
