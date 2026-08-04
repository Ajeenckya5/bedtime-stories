"""OpenAI provider.

Call path: budget -> rate limit -> cache -> breaker -> retry -> SDK.
Works with both the 1.x and legacy 0.x SDKs (the skeleton used the old one).
"""

import random
import time
from typing import Any, Dict, Optional

from ..config import MODEL, Settings
from ..errors import ConfigError, ProviderError, RateLimitedError
from ..observability.metrics import METRICS
from .base import ChatRequest, LLMResponse
from .resilience import BudgetGuard, CircuitBreaker, PromptCache, TokenBucket, retry_with_backoff


def _import_sdk():
    try:
        import openai  # type: ignore
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("openai package not installed - `pip install -r requirements.txt`") from exc
    is_v1 = hasattr(openai, "OpenAI")
    return openai, is_v1


class OpenAIProvider:
    """Thread-safe, budgeted, instrumented gpt-3.5-turbo client."""
    name = "openai"

    def __init__(self, settings: Settings, budget: Optional[BudgetGuard] = None):
        if not settings.api_key:
            raise ConfigError(
                "OPENAI_API_KEY is not set. Copy .env.example to .env and add your key, "
                "or run with BEDTIME_PROVIDER=mock for an offline demo."
            )
        self.settings = settings
        self._sdk, self._is_v1 = _import_sdk()
        self._client = None
        if self._is_v1:
            kwargs: Dict[str, Any] = {
                "api_key": settings.api_key,
                "timeout": settings.request_timeout_s,
                "max_retries": 0,  # we own retries so they are observable
            }
            if settings.base_url:
                kwargs["base_url"] = settings.base_url
            self._client = self._sdk.OpenAI(**kwargs)
        else:  # pragma: no cover - legacy SDK path
            self._sdk.api_key = settings.api_key
            if settings.base_url:
                self._sdk.api_base = settings.base_url

        self.bucket = TokenBucket(settings.rate_limit_rpm)
        self.breaker = CircuitBreaker(settings.circuit_fail_threshold, settings.circuit_reset_s)
        self.budget = budget or BudgetGuard(settings.max_usd_per_run, settings.max_usd_per_day)
        self.cache = PromptCache() if settings.enable_cache else None
        self.persistent: Any = None   # set by the orchestrator via attach_cache
        self.run_spend_usd = 0.0
        self._json_mode_supported = True  # degraded to False if the API rejects it

    def price(self, prompt_tokens: int, completion_tokens: int) -> float:
        s = self.settings
        return (
            prompt_tokens * s.prompt_usd_per_mtok + completion_tokens * s.completion_usd_per_mtok
        ) / 1_000_000

    def reset_run_spend(self) -> None:
        self.run_spend_usd = 0.0

    def attach_cache(self, persistent):
        self.persistent = persistent

    def _retryable(self):
        if self._is_v1:
            e = self._sdk
            return tuple(
                c
                for c in (
                    getattr(e, "RateLimitError", None),
                    getattr(e, "APITimeoutError", None),
                    getattr(e, "APIConnectionError", None),
                    getattr(e, "InternalServerError", None),
                    getattr(e, "APIStatusError", None),
                )
                if c is not None
            )
        return tuple(  # pragma: no cover
            c
            for c in (
                getattr(self._sdk.error, "RateLimitError", None),
                getattr(self._sdk.error, "Timeout", None),
                getattr(self._sdk.error, "APIConnectionError", None),
                getattr(self._sdk.error, "ServiceUnavailableError", None),
                getattr(self._sdk.error, "APIError", None),
            )
            if c is not None
        )

    # -- main entry point ---------------------------------------------------
    def chat(self, request: ChatRequest) -> LLMResponse:
        """One chat completion, through the full resilience stack."""
        cache_key = None
        disk_key = None
        # Only deterministic calls are cacheable. Caching a temperature-0.85
        # draft would hand every family the identical story.
        deterministic = request.temperature <= 0.0 or request.seed is not None

        if deterministic:
            if self.cache is not None:      # L1: in-process LRU
                cache_key = PromptCache.key(request.cache_key_material())
                hit = self.cache.get(cache_key)
                if hit is not None:
                    METRICS.inc("llm_cache_hits_total", stage=request.stage, tier="memory")
                    cached: LLMResponse = hit  # type: ignore[assignment]
                    return LLMResponse(
                        text=cached.text, prompt_tokens=cached.prompt_tokens,
                        completion_tokens=cached.completion_tokens, model=cached.model,
                        finish_reason=cached.finish_reason, cached=True, latency_s=0.0)

            if self.persistent is not None:  # L2: SQLite, survives restarts
                disk_key = self.persistent.llm_key(
                    request.system, request.user, request.temperature,
                    request.max_tokens, request.json_mode, request.seed)
                row = self.persistent.get("llm", disk_key)
                if row:
                    METRICS.inc("llm_cache_hits_total", stage=request.stage, tier="disk")
                    response = LLMResponse(
                        text=row["text"], prompt_tokens=row.get("prompt_tokens", 0),
                        completion_tokens=row.get("completion_tokens", 0),
                        model=MODEL, finish_reason=row.get("finish_reason", "stop"),
                        cached=True, latency_s=0.0)
                    if cache_key and self.cache is not None:
                        self.cache.put(cache_key, response)
                    return response

        # Pre-flight spend estimate keeps us inside budget even if the call is
        # expensive; the true cost is reconciled after the response arrives.
        # FIXME: rough - counts chars/4 rather than tokenising. Good enough for
        # the day-cap check, but the real cost is reconciled after the call.
        estimate = self.price(len(request.system + request.user) // 4, request.max_tokens)
        self.budget.check_and_add(self.run_spend_usd, estimate * 0.0)  # day-cap check only

        if not self.bucket.acquire(timeout=self.settings.request_timeout_s):
            METRICS.inc("llm_rate_limited_total", stage=request.stage)
            raise RateLimitedError("local rate limiter timed out waiting for a slot")

        self.breaker.before_call()
        attempts = {"n": 0}
        started = time.perf_counter()

        def _call() -> Any:
            attempts["n"] += 1
            return self._raw_call(request)

        try:
            raw = retry_with_backoff(
                _call,
                max_attempts=self.settings.max_retries,
                base_delay=self.settings.retry_base_delay_s,
                max_delay=self.settings.retry_max_delay_s,
                retry_on=self._retryable(),
                jitter=random.random,
                on_retry=lambda i, exc, d: METRICS.inc(
                    "llm_retries_total", stage=request.stage, error=type(exc).__name__
                ),
            )
        except Exception as exc:
            self.breaker.on_failure()
            METRICS.inc("llm_errors_total", stage=request.stage, error=type(exc).__name__)
            raise ProviderError(f"{request.stage}: {type(exc).__name__}: {exc}") from exc

        self.breaker.on_success()
        latency = time.perf_counter() - started
        text, ptok, ctok, finish = self._unpack(raw)

        cost = self.price(ptok, ctok)
        self.budget.check_and_add(self.run_spend_usd, cost)
        self.run_spend_usd += cost

        METRICS.inc("llm_calls_total", stage=request.stage)
        METRICS.observe("llm_latency_seconds", latency, stage=request.stage)
        METRICS.add("llm_tokens_total", ptok, stage=request.stage, kind="prompt")
        METRICS.add("llm_tokens_total", ctok, stage=request.stage, kind="completion")
        METRICS.add("llm_cost_usd_total", cost, stage=request.stage)

        response = LLMResponse(
            text=text,
            prompt_tokens=ptok,
            completion_tokens=ctok,
            model=MODEL,
            finish_reason=finish,
            latency_s=latency,
            attempts=attempts["n"],
        )
        if cache_key and self.cache is not None:
            self.cache.put(cache_key, response)
        if disk_key and self.persistent is not None:
            self.persistent.put("llm", disk_key, {
                "text": text, "prompt_tokens": ptok,
                "completion_tokens": ctok, "finish_reason": finish})
        return response

    # SDK plumbing
    def _raw_call(self, request: ChatRequest) -> Any:
        kwargs: Dict[str, Any] = {
            "model": MODEL,  # locked: never parameterised
            "messages": request.messages(),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.seed is not None:
            kwargs["seed"] = request.seed
        if request.json_mode and self._json_mode_supported:
            kwargs["response_format"] = {"type": "json_object"}

        try:
            if self._is_v1:
                return self._client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
            return self._sdk.ChatCompletion.create(**kwargs)  # pragma: no cover
        except Exception as exc:
            # Some deployments/snapshots reject response_format. Degrade once,
            # permanently, and rely on the JSON extractor instead.
            msg = str(exc).lower()
            if "response_format" in msg or "json_object" in msg:
                self._json_mode_supported = False
                kwargs.pop("response_format", None)
                METRICS.inc("llm_json_mode_disabled_total")
                if self._is_v1:
                    return self._client.chat.completions.create(**kwargs)  # type: ignore[union-attr]
                return self._sdk.ChatCompletion.create(**kwargs)  # pragma: no cover
            raise

    @staticmethod
    def _unpack(raw: Any):
        try:  # modern SDK: pydantic objects
            choice = raw.choices[0]
            text = choice.message.content or ""
            finish = getattr(choice, "finish_reason", "stop") or "stop"
            usage = getattr(raw, "usage", None)
            ptok = getattr(usage, "prompt_tokens", 0) if usage else 0
            ctok = getattr(usage, "completion_tokens", 0) if usage else 0
            return text, ptok, ctok, finish
        except AttributeError:  # pragma: no cover - legacy SDK: plain dicts
            choice = raw["choices"][0]
            usage = raw.get("usage", {})
            return (
                choice["message"]["content"] or "",
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
                choice.get("finish_reason", "stop"),
            )

    # -- moderation ---------------------------------------------------------
    def moderate(self, text: str):
        """Moderation check. Fails open but flags it in metrics."""
        if not self.settings.use_moderation_api:
            return {"available": False, "flagged": False, "reason": "disabled"}
        try:
            if self._is_v1:
                res = self._client.moderations.create(  # type: ignore[union-attr]
                    model=self.settings.moderation_model, input=text[:4000]
                )
                item = res.results[0]
                cats = {k: bool(v) for k, v in dict(item.categories).items() if v}
                scores = {k: float(v) for k, v in dict(item.category_scores).items()}
            else:  # pragma: no cover
                res = self._sdk.Moderation.create(input=text[:4000])
                item = res["results"][0]
                cats = {k: v for k, v in item["categories"].items() if v}
                scores = dict(item["category_scores"])
            top = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:5]
            METRICS.inc("moderation_checks_total", flagged=str(bool(cats)).lower())
            return {
                "available": True,
                "flagged": bool(cats),
                "categories": cats,
                "top_scores": {k: round(v, 5) for k, v in top},
            }
        except Exception as exc:
            METRICS.inc("moderation_unavailable_total", error=type(exc).__name__)
            return {"available": False, "flagged": False, "error": str(exc)[:200]}
