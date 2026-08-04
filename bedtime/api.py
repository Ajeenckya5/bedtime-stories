"""HTTP service.

Run it with:  uvicorn bedtime.api:app --port 8000
"""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .config import MODEL, get_settings
from .llm.resilience import TokenBucket
from .observability.dashboard import render_dashboard
from .observability.metrics import METRICS
from .observability.tracing import LOG
from .orchestrator import StoryOrchestrator
from .prompts import PROMPT_VERSION
from .schemas import RunStatus, StoryResult

settings = get_settings()
app = FastAPI(
    title="Bedtime Story Engine",
    version=PROMPT_VERSION,
    description="Guardrailed, judged bedtime stories for ages 5-10.",
)

_orchestrator: Optional[StoryOrchestrator] = None
_buckets: Dict[str, TokenBucket] = {}
# run_id -> result, so /feedback can revise without the client resending the story
# In-process only, so /feedback needs sticky sessions behind >1 worker.
# TODO: move to redis if this ever runs multi-node.
_recent: Dict[str, StoryResult] = {}
_RECENT_MAX = 200


def orchestrator():
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = StoryOrchestrator(settings=settings)
    return _orchestrator


def _remember(result: StoryResult):
    _recent[result.run_id] = result
    if len(_recent) > _RECENT_MAX:
        for key in list(_recent)[: len(_recent) - _RECENT_MAX]:
            _recent.pop(key, None)


# --- auth + rate limiting ---------------------------------------------------

def require_key(request: Request) -> str:
    if not settings.service_api_keys:
        return "anonymous"
    supplied = request.headers.get(settings.api_key_header, "")
    if supplied not in settings.service_api_keys:
        METRICS.inc("api_requests_total", route=request.url.path, status="401")
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return supplied[:8]


def rate_limit(request: Request, caller: str = Depends(require_key)) -> str:
    key = caller if caller != "anonymous" else (request.client.host if request.client else "local")
    bucket = _buckets.get(key)
    if bucket is None:
        bucket = _buckets[key] = TokenBucket(settings.api_rate_limit_rpm)
    if not bucket.try_acquire():
        METRICS.inc("api_requests_total", route=request.url.path, status="429")
        raise HTTPException(status_code=429, detail="rate limit exceeded, slow down")
    return caller


# schemas

class StoryRequest(BaseModel):
    request: str = Field(min_length=1, max_length=2000,
                         examples=["A story about a shy dragon's first day at school"])
    include_plan: bool = False
    include_candidates: bool = False


class FeedbackRequest(BaseModel):
    run_id: str
    feedback: str = Field(min_length=1, max_length=1000,
                          examples=["Make it a bit funnier and add a dog"])


class StoryResponse(BaseModel):
    run_id: str
    status: str
    title: str
    story: str
    message: str = ""
    quality: Dict[str, Any] = Field(default_factory=dict)
    warnings: List[str] = Field(default_factory=list)
    usage: Dict[str, Any] = Field(default_factory=dict)
    plan: Optional[Dict[str, Any]] = None
    candidates: Optional[List[Dict[str, Any]]] = None


def _to_response(result: StoryResult, include_plan: bool = False,
                 include_candidates: bool = False):
    quality: Dict[str, Any] = {}
    if result.assessment:
        a = result.assessment
        d = a.deterministic
        quality = {
            "composite": round(a.composite, 2),
            "llm_score": round(a.llm_score, 2),
            "deterministic_score": round(a.deterministic_score, 2),
            "passed_gate": a.passed,
            "judge_agreement": round(a.agreement, 3),
            "judge_samples": a.n_samples,
            "dimensions": a.dimension_medians,
            "dimension_spread": a.dimension_spread,
            "fail_reasons": a.fail_reasons,
            "readability": {
                "words": d.word_count,
                "fk_grade": d.fk_grade,
                "mean_sentence_words": d.mean_sentence_words,
                "complex_word_ratio": d.complex_word_ratio,
                "dialogue_ratio": d.dialogue_ratio,
            },
            "safety": {
                "banned_terms": d.banned_terms,
                "scary_intensity": d.scary_intensity,
                "ends_calmly": d.ends_calmly,
                "judge_flagged": a.safety_violation,
            },
            "human_voice": {
                "score": d.human_voice_score,
                "tell_density": d.ai_tell_density,
                "tells": d.ai_tells,
            },
        }
    return StoryResponse(
        run_id=result.run_id,
        status=result.status.value,
        title=result.title,
        story=result.story,
        message=result.message,
        quality=quality,
        warnings=result.warnings,
        usage={
            "model_calls": result.usage.calls,
            "cached_calls": result.usage.cached_calls,
            "prompt_tokens": result.usage.prompt_tokens,
            "completion_tokens": result.usage.completion_tokens,
            "usd": round(result.usage.usd, 5),
            "by_stage": result.usage.by_stage,
            "latency_s": round(result.latency_s, 2),
            "revisions": result.revisions_used,
        },
        plan=result.plan.model_dump() if (include_plan and result.plan) else None,
        candidates=[
            {
                "revision": c.revision,
                "source": c.source,
                "composite": round(c.assessment.composite, 2) if c.assessment else None,
                "text": c.text,
            }
            for c in result.candidates
        ] if include_candidates else None,
    )


# --- routes -----------------------------------------------------------------

@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.perf_counter()
    response = await call_next(request)
    METRICS.inc("api_requests_total", route=request.url.path,
                status=f"{response.status_code // 100}xx")
    METRICS.observe("api_latency_seconds", time.perf_counter() - started,
                    route=request.url.path)
    response.headers["x-process-time"] = f"{time.perf_counter() - started:.3f}"
    return response


@app.post("/story", response_model=StoryResponse)
def create_story(body: StoryRequest, caller: str = Depends(rate_limit)) -> StoryResponse:
    result = orchestrator().tell(body.request)
    _remember(result)
    return _to_response(result, body.include_plan, body.include_candidates)


@app.post("/feedback", response_model=StoryResponse)
def refine_story(body: FeedbackRequest, caller: str = Depends(rate_limit)) -> StoryResponse:
    previous = _recent.get(body.run_id)
    if previous is None:
        raise HTTPException(status_code=404,
                            detail="unknown run_id (results are kept in memory only)")
    result = orchestrator().refine(previous, body.feedback)
    _remember(result)
    return _to_response(result)


@app.get("/health")
def health() -> Dict[str, Any]:
    return {
        "status": "ok",
        "model": MODEL,
        "prompt_version": PROMPT_VERSION,
        "provider": settings.provider,
        "api_key_configured": bool(settings.api_key),
        "uptime_s": round(time.time() - METRICS.started_at, 1),
    }


@app.get("/ready")
def ready():
    """Readiness: refuse traffic if the upstream breaker is open."""
    provider = orchestrator().raw_provider
    breaker = getattr(provider, "breaker", None)
    state = breaker.state if breaker else "closed"
    if state == "open":
        raise HTTPException(status_code=503, detail="upstream circuit breaker is open")
    return {"status": "ready", "circuit": state, "provider": getattr(provider, "name", "?")}


@app.get("/metrics", response_class=PlainTextResponse)
def metrics() -> str:
    return METRICS.render_prometheus()


@app.get("/metrics.json")
def metrics_json():
    return METRICS.snapshot()


@app.get("/config")
def config(caller: str = Depends(require_key)) -> Dict[str, Any]:
    return settings.redacted()


@app.get("/memory/stats")
def memory_stats():
    r = orchestrator().retriever
    return r.stats() if r else {"enabled": False}


@app.get("/memory/stories")
def memory_stories(limit: int = 20):
    r = orchestrator().retriever
    if r is None:
        raise HTTPException(status_code=404, detail="memory is disabled")
    return {"stories": r.store.recent(min(limit, 100))}


@app.get("/memory/search")
def memory_search(q: str, top_k: int = 5, caller: str = Depends(rate_limit)) -> Dict[str, Any]:
    """Inspect what the retriever would inject for a given request."""
    r = orchestrator().retriever
    if r is None:
        raise HTTPException(status_code=404, detail="memory is disabled")
    found = r.recall(q)
    return {
        "summary": found.summary(),
        "block": found.block,
        "hits": [{"chunk_id": h.chunk_id, "kind": h.kind, "score": h.score,
                  "title": h.title, "text": h.text[:400]} for h in found.hits],
    }


@app.delete("/memory/stories/{story_id}")
def memory_forget(story_id: str, caller: str = Depends(require_key)) -> Dict[str, Any]:
    """Right to be forgotten - stories are personal data about a child."""
    r = orchestrator().retriever
    if r is None:
        raise HTTPException(status_code=404, detail="memory is disabled")
    if not r.store.forget(story_id):
        raise HTTPException(status_code=404, detail="unknown story_id")
    return {"forgotten": story_id}


@app.get("/cache/stats")
def cache_stats():
    return orchestrator().cache.stats()


@app.post("/cache/invalidate")
def cache_invalidate(namespace: Optional[str] = None,
                     caller: str = Depends(require_key)) -> Dict[str, Any]:
    removed = orchestrator().cache.invalidate(namespace)
    return {"removed": removed, "namespace": namespace or "all"}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return render_dashboard(settings.trace_dir, METRICS.snapshot(), settings)


@app.on_event("startup")
def _startup() -> None:
    LOG.info("bedtime api up | model=%s prompts=%s provider=%s auth=%s",
             MODEL, PROMPT_VERSION, settings.provider,
             "on" if settings.service_api_keys else "off")
