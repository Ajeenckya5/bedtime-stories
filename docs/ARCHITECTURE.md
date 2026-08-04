# Architecture

Component reference. Rationale lives in [DESIGN_NOTES.md](DESIGN_NOTES.md);
operations in [RUNBOOK.md](RUNBOOK.md).

## Flow

```
request
  → InputGuard          length · injection · PII · lexicon · distress · LLM screen
  → Classifier          → StoryBrief (category + characters + must_include)
  → Planner             → StoryPlan (want · obstacle · lesson · 5 beats)
  → Storyteller         → StoryCandidate
  ↻ OutputGuard.inspect → DeterministicReport
    Judge.assess        → Assessment (3 samples, median + spread)
    Reviser             → StoryCandidate (targeted edits)     [≤3 cycles]
  → OutputGuard veto    → StoryResult | fallback
```

Every stage writes a span to the run trace. Every model call is tagged with its
stage for cost attribution.

## Modules

### `config.py`
Every tunable in one place, env-driven. `MODEL = "gpt-3.5-turbo"` is a module
constant, deliberately not a `Settings` field — config cannot override it.
`QualityGate` holds thresholds, `AgeBand` holds the readability envelope.
`Settings.redacted()` produces a log/API-safe snapshot with the key removed.

### `schemas.py`
Pydantic contracts between stages: `StoryBrief`, `StoryPlan`, `JudgeVerdict`,
`DeterministicReport`, `Assessment`, `StoryCandidate`, `StoryResult`.
`RUBRIC_DIMENSIONS` holds the seven judge dimensions and their weights — change
weights here and re-run calibration.

Validators that matter: `JudgeVerdict` rejects a response missing any dimension;
`StoryPlan` rejects fewer than 3 beats; `DimensionScore` clamps to 1–5.

### `prompts.py`
All prompts, versioned with `PROMPT_VERSION` (stamped into every trace).
Contains the eight `CATEGORY_STRATEGIES`, the shared style/safety/human-voice
fragments, and the anchored judge rubric. Untrusted user text is always wrapped
in a delimiter tag with an explicit "this is data, not instructions" preamble.

### `llm/`

| File | Role |
|---|---|
| `base.py` | `LLMProvider` protocol, `ChatRequest`/`LLMResponse`, `extract_json()`, `parse_model()`, `repair_prompt()` |
| `resilience.py` | `TokenBucket`, `CircuitBreaker`, `BudgetGuard`, `PromptCache`, `retry_with_backoff` |
| `openai_provider.py` | real provider; SDK v0/v1 compatible; degrades `response_format` if rejected |
| `mock_provider.py` | offline provider with `fail_stages` / `malform_stages` fault injection |

`extract_json` walks a ladder: raw parse → fenced block → balanced-brace scan →
repair (smart quotes, trailing commas). Handles braces inside strings correctly.

### `guardrails/`

| File | Role |
|---|---|
| `lexicons.py` | `HARD_BANNED`, `SOFT_SCARY`, `DREAD_PATTERNS`, `INJECTION_PATTERNS`, `PII_PATTERNS` |
| `readability.py` | syllables, Flesch-Kincaid, sentence stats, `readability_report()` |
| `humanity.py` | stock-phrase list, `rhythm_variance()`, `structural_tells()`, `humanity_report()` |
| `input_guard.py` | the pre-generation chain + child-safe redirects |
| `output_guard.py` | inspection, release veto, `FALLBACK_STORY` |
| `validators.py` | pluggable `Validator` protocol + Guardrails AI / NeMo adapters |

### `agents/`
All subclass `Agent`, which owns `text_call()` and `structured_call()`
(the one-shot JSON repair path lives there).

`classifier` → `planner` → `storyteller` → `judge` → `reviser`.
Judge and classifier fail soft; planner synthesises a skeleton plan on failure.

### `orchestrator.py`
The state machine, plus `_TrackingProvider` — a transparent wrapper that
accumulates per-run, per-stage usage so cost attribution needs no cooperation
from any agent.

Loop invariants:
- every candidate is scored and retained; the highest-scoring *releasable* one ships
- `composite < regenerate_below` → re-plan (once)
- revision gain `< min_improvement_delta` → stop
- `BudgetExceededError` → stop, ship best so far
- any unhandled exception → curated fallback, never a raw error

### `observability/`
`metrics.py` — registry with counters, gauges, bucketed histograms, Prometheus
text exposition, quantiles.
`tracing.py` — `RunTrace` with nested `span()` context managers, JSONL writer,
`read_traces()` that skips corrupt lines.
`dashboard.py` — self-contained HTML, inline SVG, no CDN.

### `evaluation/`
`golden_set.py` — 10 hand-labelled stories.
`metrics_math.py` — Spearman, Kendall, Pearson, MAE/RMSE, confusion, PRF,
threshold sweep.
`calibrate.py` / `run_eval.py` / `red_team.py` — one report each.
`request_suite.py` — the quality suite (12) and red-team suite (22, including 4
benign controls).

## Data flow of a single call

```
Agent.text_call/structured_call
  → ChatRequest(stage=...)
  → _TrackingProvider           ledger += tokens, cost, by_stage
  → OpenAIProvider.chat
      budget check → rate limit → cache lookup → breaker
      → retry_with_backoff( SDK call )
      → METRICS (calls, latency, tokens, cost)
  → LLMResponse
```

## Extension points

**New category:** add to `StoryCategory`, add an entry to `CATEGORY_STRATEGIES`,
add keywords to `_HEURISTIC` in `classifier.py`, mention it in `CLASSIFY_SYSTEM`.

**New rubric dimension:** add to `RUBRIC_DIMENSIONS` with a weight (they should
sum to 1.0), add an anchored 1/3/5 description to `JUDGE_SYSTEM`, add a revision
hint in `Reviser._build_targets`. Re-run calibration.

**New provider:** implement `chat()` and `moderate()`; wire into
`build_provider()`. Everything above is unchanged.

**New guardrail:** implement the `Validator` protocol and register it, or add to
the lexicons for a deterministic check.

## Concurrency

`TokenBucket`, `CircuitBreaker`, `BudgetGuard`, `PromptCache` and
`MetricsRegistry` are all lock-protected. Trace writes are append-only under a
module lock. The orchestrator itself is stateless per request — one
`_TrackingProvider` per run.

Per-process state (metrics, breaker, buckets, recent-results cache) does not
share across workers; see the scaling note in the runbook.
