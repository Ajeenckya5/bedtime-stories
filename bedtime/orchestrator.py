"""Pipeline orchestration.

screen -> classify -> plan -> draft -> [validate + judge -> revise]* -> release

Loop rules: keep the best candidate, re-plan below regenerate_below, stop when a
revision gains less than min_improvement_delta. See docs/DESIGN_NOTES.md.
"""

import time
from typing import Any, Dict, List, Optional, Tuple

from .agents.classifier import Classifier
from .agents.judge import Judge
from .agents.planner import Planner
from .agents.reviser import Reviser
from .agents.storyteller import Storyteller
from .config import MODEL, Settings, get_settings
from .errors import BedtimeError, BudgetExceededError, ProviderError, UnsafeRequestError
from .guardrails.input_guard import InputGuard
from .guardrails.output_guard import OutputGuard
from .guardrails.validators import configure_from_env
from .llm.base import ChatRequest, LLMProvider, LLMResponse
from pydantic import ValidationError

from .llm.cache import PersistentCache
from .memory.retriever import Retriever
from .storage import StorageUnavailable
from .observability.metrics import METRICS
from .observability.tracing import LOG, RunTrace
from .prompts import PROMPT_VERSION
from .schemas import (
    Assessment,
    RunStatus,
    SafetyDecision,
    StoryBrief,
    StoryCandidate,
    StoryPlan,
    StoryResult,
    UsageLedger,
)


class _TrackingProvider:
    """Transparent wrapper that accumulates per-run, per-stage usage.

    Sits between the agents and the real provider so cost attribution needs no
    cooperation from any agent - they just make calls.
    """
    def __init__(self, inner: LLMProvider, settings: Settings) -> None:
        self._inner = inner
        self._settings = settings
        self.name = getattr(inner, "name", "unknown")
        self.ledger = UsageLedger()

    def chat(self, request: ChatRequest) -> LLMResponse:
        response = self._inner.chat(request)
        self.ledger.calls += 1
        if response.cached:
            self.ledger.cached_calls += 1
        self.ledger.prompt_tokens += response.prompt_tokens
        self.ledger.completion_tokens += response.completion_tokens
        self.ledger.by_stage[request.stage] = (
            self.ledger.by_stage.get(request.stage, 0) + response.total_tokens
        )
        price = getattr(self._inner, "price", None)
        if callable(price):
            self.ledger.usd += price(response.prompt_tokens, response.completion_tokens)
        return response

    def moderate(self, text: str):
        return self._inner.moderate(text)

    def reset(self) -> None:
        self.ledger = UsageLedger()
        reset = getattr(self._inner, "reset_run_spend", None)
        if callable(reset):
            reset()


def build_provider(settings: Optional[Settings] = None) -> LLMProvider:
    """Provider selection. Falls back to mock (loudly) if no key is present."""
    settings = settings or get_settings()
    if settings.provider == "mock" or not settings.api_key:
        from .llm.mock_provider import MockProvider

        if settings.provider != "mock":
            LOG.warning("OPENAI_API_KEY not set - running with the offline mock provider")
        return MockProvider(settings=settings)
    from .llm.openai_provider import OpenAIProvider

    return OpenAIProvider(settings)


class StoryOrchestrator:
    def __init__(self, provider: Optional[LLMProvider] = None,
                 settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.raw_provider = provider or build_provider(self.settings)
        configure_from_env()

        self.cache = PersistentCache(
            db_path=self.settings.cache_db,
            model=MODEL,
            prompt_version=PROMPT_VERSION,
            ttl_days=self.settings.cache_ttl_days,
            enabled=self.settings.enable_cache,
        )
        # Editing a prompt should not silently serve output from the old one.
        self.cache.invalidate_stale_versions()
        # Let the provider share it, so deterministic calls survive restarts.
        if hasattr(self.raw_provider, "attach_cache"):
            self.raw_provider.attach_cache(self.cache)

        self.retriever: Optional[Retriever] = None
        if self.settings.memory_enabled:
            try:
                self.retriever = Retriever(self.settings)
            except Exception as exc:
                LOG.warning("memory unavailable, continuing without it: %s", exc)

    # public API
    def tell(self, request: str, request_id: Optional[str] = None):
        """Generate a story. Never raises - worst case returns the fallback."""
        provider = _TrackingProvider(self.raw_provider, self.settings)
        provider.reset()
        trace = RunTrace(
            run_id=request_id,
            trace_dir=self.settings.trace_dir,
            redact_text=self.settings.redact_story_text_in_traces,
            metadata={
                "model": MODEL,
                "prompt_version": PROMPT_VERSION,
                "provider": provider.name,
                "accept_threshold": self.settings.gate.accept_threshold,
                "judge_samples": self.settings.gate.judge_samples,
                "max_revisions": self.settings.gate.max_revisions,
                "request_chars": len(request or ""),
            },
        )
        result = StoryResult(run_id=trace.run_id)
        started = time.perf_counter()

        try:
            result = self._run(request, provider, trace, result)
        except BudgetExceededError as exc:
            result = self._degrade(result, provider, trace, RunStatus.FALLBACK,
                                   f"budget: {exc}", exc.user_message)
        except (ProviderError, BedtimeError) as exc:
            result = self._degrade(result, provider, trace, RunStatus.ERROR,
                                   f"{type(exc).__name__}: {exc}", exc.user_message)
        except Exception as exc:  # pragma: no cover - last line of defence
            LOG.exception("unexpected failure in run %s", trace.run_id)
            result = self._degrade(result, provider, trace, RunStatus.ERROR,
                                   f"unexpected: {type(exc).__name__}: {exc}",
                                   "Something went wrong while writing your story.")

        result.latency_s = time.perf_counter() - started
        result.usage = provider.ledger
        METRICS.inc("stories_total", status=result.status.value)
        METRICS.observe("story_latency_seconds", result.latency_s)
        METRICS.inc("story_revisions_total", count=str(result.revisions_used),
                    status=result.status.value)
        trace.set_result(result.summary())
        trace.write()
        return result

    def refine(self, previous: StoryResult, feedback: str) -> StoryResult:
        """Apply user feedback to an existing story. Re-screens the feedback."""
        provider = _TrackingProvider(self.raw_provider, self.settings)
        provider.reset()
        trace = RunTrace(trace_dir=self.settings.trace_dir,
                         metadata={"model": MODEL, "prompt_version": PROMPT_VERSION,
                                   "kind": "refine", "parent_run": previous.run_id})
        result = StoryResult(run_id=trace.run_id, brief=previous.brief, plan=previous.plan)
        started = time.perf_counter()

        try:
            guard = InputGuard(provider, self.settings)
            with trace.span("screen_feedback"):
                verdict = guard.screen(feedback, trace)
            if verdict.decision == SafetyDecision.REFUSE:
                result.status = RunStatus.REFUSED
                result.title, result.story = previous.title, previous.story
                result.message = verdict.user_message
                METRICS.inc("stories_total", status="refused_feedback")
                trace.set_result(result.summary())
                trace.write()
                return result

            brief = previous.brief or StoryBrief(raw_request=feedback,
                                                 sanitized_request=verdict.sanitized_request)
            base = StoryCandidate(title=previous.title, text=previous.story, source="draft")
            base_assessment = previous.assessment or Assessment()
            # The user's wish is the highest-priority fix, ahead of the judge's.
            base_assessment = base_assessment.model_copy(deep=True)
            base_assessment.must_fix = [
                f"The family asked for this change - apply it fully: {verdict.sanitized_request}"
            ] + base_assessment.must_fix[:2]

            reviser = Reviser(provider, self.settings, trace)
            with trace.span("revise_from_feedback"):
                candidate = reviser.run(base, base_assessment, brief, revision=1)

            candidate, assessment = self._score(candidate, brief, provider, trace)
            result = self._finalise(result, [candidate], brief, previous.plan, provider, trace)
            result.revisions_used = 1
        except BedtimeError as exc:
            result = self._degrade(result, provider, trace, RunStatus.ERROR,
                                   str(exc), exc.user_message)

        result.latency_s = time.perf_counter() - started
        result.usage = provider.ledger
        trace.set_result(result.summary())
        trace.write()
        return result

    # -- pipeline -----------------------------------------------------------
    def _run(self, request: str, provider: _TrackingProvider, trace: RunTrace,
             result: StoryResult):
        gate = self.settings.gate

        # 1. input guardrail ------------------------------------------------
        guard_in = InputGuard(provider, self.settings)
        with trace.span("input_guard"):
            verdict = guard_in.screen(request, trace)
        if verdict.decision == SafetyDecision.REFUSE:
            result.status = RunStatus.REFUSED
            result.message = verdict.user_message
            result.warnings = verdict.reasons
            METRICS.inc("guardrail_blocks_total", guardrail="input", reason="refused")
            return result
        if verdict.decision == SafetyDecision.SANITIZE:
            result.warnings.append("request_sanitized: " + ", ".join(verdict.reasons[:3]))

        # 1b. story cache ---------------------------------------------------
        # Off by default. When on, a near-identical request short-circuits the
        # whole pipeline - useful for demos and load tests, risky for children.
        if self.settings.story_cache_enabled:
            cached = self.cache.get("story", self.cache.story_key(verdict.sanitized_request))
            if cached:
                trace.event("story_cache_hit", title=cached.get("title", ""))
                result.status = RunStatus.OK
                result.title = cached.get("title", "")
                result.story = cached.get("story", "")
                result.warnings.append("served from story cache")
                return result

        # 2. classify -------------------------------------------------------
        classifier = Classifier(provider, self.settings, trace)
        with trace.span("classify"):
            brief = classifier.run(verdict.sanitized_request, raw_request=request)
        result.brief = brief

        # 2b. recall past stories -------------------------------------------
        continuity = ""
        if self.retriever is not None:
            with trace.span("memory_recall"):
                recalled = self.retriever.recall(
                    verdict.sanitized_request, brief.characters, trace)
            continuity = recalled.block
            if recalled.found:
                result.warnings.append(
                    "continuity from: " + ", ".join(
                        s.get("title", "") for s in recalled.stories[:2]))

        # 3. plan + 4. draft ------------------------------------------------
        planner = Planner(provider, self.settings, trace)
        storyteller = Storyteller(provider, self.settings, trace)
        reviser = Reviser(provider, self.settings, trace)

        plan = self._plan_with_cache(planner, brief, continuity, trace)
        result.plan = plan
        with trace.span("draft"):
            candidate = storyteller.run(plan, brief, revision=0, source="draft",
                                        continuity=continuity)

        candidates: List[StoryCandidate] = []
        regenerations = 0

        # 5. judge / revise loop --------------------------------------------
        for cycle in range(gate.max_revisions + 1):
            with trace.span("evaluate", cycle=cycle):
                candidate, assessment = self._score(candidate, brief, provider, trace)
            candidates.append(candidate)

            if assessment.passed:
                trace.event("gate_passed", cycle=cycle, composite=round(assessment.composite, 1))
                break
            if cycle >= gate.max_revisions:
                trace.event("revisions_exhausted", cycle=cycle,
                            composite=round(assessment.composite, 1))
                break

            # Stop if the last revision failed to move the needle.
            if len(candidates) >= 2 and candidates[-2].assessment:
                delta = assessment.composite - candidates[-2].assessment.composite
                if delta < gate.min_improvement_delta and assessment.composite >= gate.regenerate_below:
                    trace.event("revision_stalled", delta=round(delta, 2))
                    METRICS.inc("revision_stalled_total")
                    break

            try:
                if assessment.composite < gate.regenerate_below and regenerations < 1:
                    # Unsalvageable: re-plan rather than polish.
                    regenerations += 1
                    trace.event("regenerating", composite=round(assessment.composite, 1))
                    METRICS.inc("regenerations_total")
                    with trace.span("replan", cycle=cycle):
                        # Never reuse a cached plan here - the cached one is
                        # exactly what just failed.
                        plan = planner.run(brief, continuity)
                    result.plan = plan
                    with trace.span("redraft", cycle=cycle):
                        candidate = storyteller.run(plan, brief, revision=cycle + 1,
                                                    source="regeneration",
                                                    continuity=continuity)
                else:
                    with trace.span("revise", cycle=cycle):
                        candidate = reviser.run(candidate, assessment, brief, revision=cycle + 1)
            except BudgetExceededError:
                trace.event("budget_stop", cycle=cycle)
                METRICS.inc("budget_stops_total")
                break

            result.revisions_used = cycle + 1

        return self._finalise(result, candidates, brief, plan, provider, trace)

    def _plan_with_cache(self, planner: Planner, brief: StoryBrief, continuity: str,
                         trace: RunTrace):
        # Skip the cache when continuity applies - a follow-up must not reuse the
        # plan of the story it follows.
        use_cache = self.settings.plan_cache_enabled and not continuity
        key = self.cache.plan_key(brief) if use_cache else ""

        if use_cache:
            cached = self.cache.get("plan", key)
            if cached:
                try:
                    plan = StoryPlan.model_validate(cached)
                    trace.event("plan_cache_hit", title=plan.title)
                    return plan
                except ValidationError as exc:
                    # Schema changed under a cached entry - drop it and re-plan.
                    # (Was `except Exception` and it was quietly swallowing a
                    # missing import, so cache hits never actually got reused.)
                    LOG.warning("stale plan cache entry, dropping: %s", exc)
                    self.cache.put("plan", key, None, ttl_seconds=0)

        with trace.span("plan"):
            plan = planner.run(brief, continuity)
        if use_cache:
            self.cache.put("plan", key, plan.model_dump())
        return plan

    def _score(self, candidate: StoryCandidate, brief: StoryBrief,
               provider: _TrackingProvider, trace: RunTrace) -> Tuple[StoryCandidate, Assessment]:
        guard_out = OutputGuard(provider, self.settings)
        det, moderation = guard_out.inspect(candidate.text, trace)
        judge = Judge(provider, self.settings, trace)
        assessment = judge.assess(candidate.text, brief, det)
        if moderation.get("flagged"):
            assessment.safety_violation = True
            assessment.passed = False
            if "moderation flagged" not in " ".join(assessment.fail_reasons):
                assessment.fail_reasons.append("moderation flagged the story")
        candidate.assessment = assessment
        return candidate, assessment

    # -- finalisation -------------------------------------------------------
    def _finalise(self, result: StoryResult, candidates: List[StoryCandidate],
                  brief: StoryBrief, plan, provider: _TrackingProvider,
                  trace: RunTrace) -> StoryResult:
        scored = [c for c in candidates if c.assessment]
        result.candidates = candidates
        result.brief = result.brief or brief
        result.plan = result.plan or plan

        if not scored:
            return self._degrade(result, provider, trace, RunStatus.FALLBACK,
                                 "no scored candidate", "")

        guard_out = OutputGuard(provider, self.settings)
        # Best first; take the best candidate that is actually releasable.
        for candidate in sorted(scored, key=lambda c: c.assessment.composite, reverse=True):
            a = candidate.assessment
            releasable, blockers = guard_out.is_releasable(a.deterministic, a.safety_violation)
            if not releasable:
                trace.event("candidate_vetoed", revision=candidate.revision,
                            blockers="; ".join(blockers)[:200])
                continue

            result.title = candidate.title
            result.story = candidate.text
            result.assessment = a
            if a.passed:
                result.status = RunStatus.OK
            else:
                result.status = RunStatus.OK_DEGRADED
                result.message = (
                    "This one came out good but not quite great - "
                    "ask me to try again if you'd like a different version."
                )
                result.warnings.extend(a.fail_reasons[:4])
                METRICS.inc("degraded_releases_total")
            trace.event("released", status=result.status.value, revision=candidate.revision,
                        composite=round(a.composite, 1))
            self._persist(result, trace)
            return result

        # Everything was vetoed on safety.
        return self._degrade(result, provider, trace, RunStatus.FALLBACK,
                             "all candidates vetoed by output guard", "")

    def _persist(self, result: StoryResult, trace: RunTrace):
        """Index the released story and, if enabled, cache it."""
        if not result.story:
            return
        if self.retriever is not None:
            self.retriever.remember(
                story_id=result.run_id,
                run_id=result.run_id,
                title=result.title,
                story=result.story,
                brief=result.brief,
                plan=result.plan,
                composite=result.assessment.composite if result.assessment else None,
                trace=trace,
            )
        # Only cache stories that cleanly passed the gate. Caching a degraded
        # one means serving known-mediocre output over and over.
        if (self.settings.story_cache_enabled and result.status is RunStatus.OK
                and result.brief is not None):
            self.cache.put("story", self.cache.story_key(result.brief.sanitized_request),
                           {"title": result.title, "story": result.story})

    def _degrade(self, result: StoryResult, provider: _TrackingProvider, trace: RunTrace,
                 status: RunStatus, reason: str, user_message: str) -> StoryResult:
        LOG.warning("[%s] degrading to fallback: %s", trace.run_id, reason)
        guard_out = OutputGuard(provider, self.settings)
        title, story = guard_out.fallback(reason, trace)
        result.status = status
        result.title = title
        result.story = story
        result.message = user_message or (
            "Here's one of my favourite stories instead - I hope you like it."
        )
        result.warnings.append(reason[:200])
        return result
