import json

import pytest

from bedtime.agents.base import strip_title
from bedtime.config import MODEL, QualityGate, Settings
from bedtime.errors import BudgetExceededError, CircuitOpenError, StructuredOutputError
from bedtime.llm.base import ChatRequest, extract_json
from bedtime.llm.mock_provider import MockProvider
from bedtime.llm.resilience import BudgetGuard, CircuitBreaker, PromptCache, TokenBucket
from bedtime.observability.metrics import MetricsRegistry
from bedtime.observability.tracing import RunTrace, read_traces
from bedtime.orchestrator import StoryOrchestrator
from bedtime.schemas import RUBRIC_DIMENSIONS, JudgeVerdict, RunStatus, StoryPlan


@pytest.fixture
def settings(tmp_path):
    return Settings(provider="mock", use_moderation_api=False, trace_dir=tmp_path / "traces",
                    gate=QualityGate(judge_samples=2, max_revisions=1))


def orchestrator(settings, **mock_kwargs):
    return StoryOrchestrator(MockProvider(settings=settings, **mock_kwargs), settings)


# --- model lock ------------------------------------------------------------

def test_model_is_locked_to_gpt_35_turbo():
    assert MODEL == "gpt-3.5-turbo"
    # It must not be reachable through Settings - config cannot override it.
    assert not hasattr(Settings(), "model")


# --- JSON handling ---------------------------------------------------------

@pytest.mark.parametrize("raw", [
    '{"a": 1}',
    'Sure! Here you go:\n```json\n{"a": 1}\n```',
    'Here is the result: {"a": 1} Hope that helps!',
    '{"a": 1,}',
    '{“a”: 1}',
])
def test_extract_json_survives_chatty_models(raw):
    assert extract_json(raw)["a"] == 1


def test_extract_json_raises_on_garbage():
    with pytest.raises(StructuredOutputError):
        extract_json("there is no json here at all")


def test_extract_json_handles_braces_inside_strings():
    assert extract_json('{"t": "a } brace"}')["t"] == "a } brace"


@pytest.mark.parametrize("raw,title", [
    ("TITLE: The Blue Cat\n\nOnce there was...", "The Blue Cat"),
    ("**TITLE:** The Blue Cat\n\nOnce...", "The Blue Cat"),
    ("Title - The Blue Cat\n\nOnce...", "The Blue Cat"),
])
def test_strip_title_variants(raw, title):
    assert strip_title(raw)[0] == title


# --- schema validation -----------------------------------------------------

def test_judge_verdict_rejects_missing_dimensions():
    partial = {"scores": {"engagement": {"score": 4}}, "must_fix": []}
    with pytest.raises(Exception):
        JudgeVerdict.model_validate(partial)


def test_judge_verdict_rejects_out_of_range_score():
    scores = {d: {"score": 9} for d in RUBRIC_DIMENSIONS}
    with pytest.raises(Exception):
        JudgeVerdict.model_validate({"scores": scores})


def test_story_plan_requires_beats():
    with pytest.raises(Exception):
        StoryPlan(title="t", logline="l", protagonist="p", want="w",
                  obstacle="o", lesson="x", beats=[])


# --- resilience ------------------------------------------------------------

def test_token_bucket_limits_burst():
    bucket = TokenBucket(rate_per_minute=60, burst=3)
    assert sum(bucket.try_acquire() for _ in range(10)) == 3


def test_circuit_breaker_opens_then_half_opens():
    breaker = CircuitBreaker(fail_threshold=2, reset_after_s=0.05)
    breaker.on_failure()
    breaker.on_failure()
    assert breaker.state == "open"
    with pytest.raises(CircuitOpenError):
        breaker.before_call()
    import time
    time.sleep(0.06)
    assert breaker.state == "half_open"
    breaker.on_success()
    assert breaker.state == "closed"


def test_budget_guard_enforces_per_run_cap():
    guard = BudgetGuard(max_usd_per_run=0.01, max_usd_per_day=100)
    guard.check_and_add(0.005, 0.004)
    with pytest.raises(BudgetExceededError):
        guard.check_and_add(0.009, 0.005)


def test_prompt_cache_evicts_lru():
    cache = PromptCache(max_entries=2)
    cache.put("a", 1); cache.put("b", 2); cache.get("a"); cache.put("c", 3)
    assert cache.get("b") is None and cache.get("a") == 1


# --- metrics ---------------------------------------------------------------

def test_prometheus_exposition_is_wellformed():
    m = MetricsRegistry()
    m.inc("llm_calls_total", stage="draft")
    m.observe("llm_latency_seconds", 2.5, stage="draft")
    text = m.render_prometheus()
    assert '# TYPE llm_calls_total counter' in text
    assert 'llm_calls_total{stage="draft"} 1.0' in text
    assert 'llm_latency_seconds_bucket{stage="draft",le="4"} 1' in text
    assert 'llm_latency_seconds_count{stage="draft"} 1' in text


def test_histogram_quantiles():
    m = MetricsRegistry()
    for v in [0.1, 0.3, 1.5, 2.0, 30.0]:
        m.observe("story_latency_seconds", v)
    snap = m.snapshot()["histograms"]["story_latency_seconds"]
    stats = list(snap.values())[0]
    assert stats["count"] == 5 and stats["p95"] >= stats["p50"]


# --- tracing ---------------------------------------------------------------

def test_trace_roundtrip(tmp_path):
    trace = RunTrace(trace_dir=tmp_path)
    with trace.span("plan", cycle=0):
        trace.event("planned", beats=5)
    trace.set_result({"status": "ok", "composite": 88.0})
    trace.write()
    rows = read_traces(tmp_path)
    assert len(rows) == 1
    assert rows[0]["spans"][0]["name"] == "plan"
    assert rows[0]["spans"][0]["events"][0]["message"] == "planned"


def test_read_traces_skips_corrupt_lines(tmp_path):
    (tmp_path / "2026-01-01.jsonl").write_text('{"run_id":"a"}\nNOT JSON\n{"run_id":"b"}\n')
    assert len(read_traces(tmp_path)) == 2


# --- orchestrator end to end -----------------------------------------------

def test_happy_path(settings):
    result = orchestrator(settings).tell("a story about Alice and her cat Bob")
    assert result.status is RunStatus.OK
    assert result.assessment and result.assessment.passed
    assert "Alice" in result.story
    assert result.usage.calls > 0
    assert len(result.assessment.dimension_medians) == len(RUBRIC_DIMENSIONS)


def test_unsafe_request_is_refused_without_generating(settings):
    provider = MockProvider(settings=settings)
    result = StoryOrchestrator(provider, settings).tell("a knight who kills with a gun")
    assert result.status is RunStatus.REFUSED
    assert not result.story
    # Blocked by the lexicon, so it must not have reached the storyteller.
    assert not any(c.stage == "draft" for c in provider.calls)


def test_provider_failure_degrades_to_fallback(settings):
    result = orchestrator(settings, fail_stages={"draft"}).tell("a story about a bear")
    assert result.status in {RunStatus.FALLBACK, RunStatus.ERROR}
    assert result.story  # a story is always returned
    assert "Lamp" in result.title or result.story


def test_malformed_judge_json_is_repaired(settings):
    provider = MockProvider(settings=settings, malform_stages={"judge"})
    result = StoryOrchestrator(provider, settings).tell("a story about a fox")
    assert result.status is RunStatus.OK
    assert any(c.stage == "judge_repair" for c in provider.calls)


def test_moderation_flag_blocks_release(settings):
    s = settings.__class__(**{**settings.__dict__, "use_moderation_api": True})
    provider = MockProvider(settings=s, moderation_flag=True)
    result = StoryOrchestrator(provider, s).tell("a story about a duck")
    assert result.status is RunStatus.FALLBACK


def test_best_candidate_is_kept_never_a_worse_revision(settings):
    result = orchestrator(settings).tell("a story about a whale")
    scored = [c for c in result.candidates if c.assessment]
    if scored and result.assessment:
        assert result.assessment.composite == max(c.assessment.composite for c in scored)


def test_feedback_is_rescreened(settings):
    o = orchestrator(settings)
    first = o.tell("a story about a rabbit")
    refined = o.refine(first, "now make it violent with a gun")
    assert refined.status is RunStatus.REFUSED
    assert refined.story == first.story  # original preserved, not replaced


def test_feedback_applies_benign_change(settings):
    o = orchestrator(settings)
    first = o.tell("a story about a rabbit")
    refined = o.refine(first, "make it a bit funnier please")
    assert refined.status in {RunStatus.OK, RunStatus.OK_DEGRADED}


def test_trace_written_per_run(settings):
    orchestrator(settings).tell("a story about a mouse")
    rows = read_traces(settings.trace_dir)
    assert rows and rows[0]["metadata"]["model"] == MODEL
    assert rows[0]["result"]["status"] in {"ok", "ok_degraded"}


def test_protagonist_name_is_clean_when_request_names_nobody(settings):
    """Regression: the hero used to render as a stray backslash when the
    request contained no explicit name, because a quoted JSON token survived
    into the plan. Nothing in the delivered story should be punctuation-only."""
    import re

    result = orchestrator(settings).tell("a silly penguin chef")
    assert result.plan is not None
    assert re.fullmatch(r"[A-Z][a-z]+.*", result.plan.protagonist), result.plan.protagonist
    assert '"' not in result.plan.protagonist
    assert "named \\" not in result.story
    assert not re.search(r"\bnamed [^A-Za-z]", result.story)


def test_result_serialises_to_json(settings):
    result = orchestrator(settings).tell("a story about a star")
    json.dumps(result.model_dump(mode="json"), default=str)
