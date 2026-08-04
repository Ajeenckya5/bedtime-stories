"""Pydantic models passed between pipeline stages."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


def new_id(prefix: str):
    return f"{prefix}_{uuid.uuid4().hex[:12]}"

# Request understanding

class StoryCategory(str, Enum):
    """Request taxonomy. Each category gets a tailored generation strategy
    (different arc template, pacing and prompt emphasis) - see agents/strategies.py.
    """
    ANIMAL_FRIENDSHIP = "animal_friendship"
    ADVENTURE_QUEST = "adventure_quest"
    MAGIC_WONDER = "magic_wonder"
    EVERYDAY_COURAGE = "everyday_courage"
    BEDTIME_LULLABY = "bedtime_lullaby"
    SILLY_HUMOR = "silly_humor"
    CURIOSITY_LEARNING = "curiosity_learning"
    FAMILY_BELONGING = "family_belonging"


class SafetyDecision(str, Enum):
    ALLOW = "allow"
    SANITIZE = "sanitize"   # proceed, but strip/reframe the problematic element
    REFUSE = "refuse"       # do not generate; return a gentle redirect


class InputAssessment(BaseModel):
    """Output of the input guardrail stage."""
    decision: SafetyDecision = SafetyDecision.ALLOW
    reasons: List[str] = Field(default_factory=list)
    injection_detected: bool = False
    pii_found: List[str] = Field(default_factory=list)
    sanitized_request: str = ""
    user_message: str = ""       # shown to the user on REFUSE
    detector_scores: Dict[str, float] = Field(default_factory=dict)


class StoryBrief(BaseModel):
    """Structured interpretation of a free-text request."""
    raw_request: str
    sanitized_request: str
    category: StoryCategory = StoryCategory.MAGIC_WONDER
    characters: List[str] = Field(default_factory=list)
    setting: str = ""
    themes: List[str] = Field(default_factory=list)
    tone: str = "warm"
    target_age: int = 7
    must_include: List[str] = Field(default_factory=list)
    classification_confidence: float = 0.5

    @field_validator("target_age")
    @classmethod
    def _clamp_age(cls, v: int) -> int:
        return max(5, min(10, v))


class StoryBeat(BaseModel):
    name: str
    purpose: str
    content: str


class StoryPlan(BaseModel):
    """The beat sheet. Planning before drafting is what produces a real arc
    instead of a flat sequence of events."""
    title: str
    logline: str
    protagonist: str
    want: str          # what the protagonist pursues
    obstacle: str      # what stands in the way
    lesson: str        # the gentle takeaway
    beats: List[StoryBeat] = Field(default_factory=list)
    sensory_motifs: List[str] = Field(default_factory=list)
    calming_ending: str = ""

    @field_validator("beats")
    @classmethod
    def _min_beats(cls, v: List[StoryBeat]):
        if len(v) < 3:
            raise ValueError("a usable plan needs at least 3 beats")
        return v

# Judging

RUBRIC_DIMENSIONS: Dict[str, float] = {
    "age_appropriateness": 0.20,
    "narrative_arc": 0.18,
    "engagement": 0.17,
    "language_fit": 0.16,
    "human_voice": 0.14,
    "bedtime_suitability": 0.09,
    "prompt_adherence": 0.06,
}


class DimensionScore(BaseModel):
    score: float = Field(ge=1.0, le=5.0)
    justification: str = ""


class JudgeVerdict(BaseModel):
    """One judge sample."""
    scores: Dict[str, DimensionScore]
    safety_violation: bool = False
    safety_notes: str = ""
    must_fix: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    overall_comment: str = ""

    @field_validator("scores")
    @classmethod
    def _all_dimensions(cls, v: Dict[str, DimensionScore]):
        missing = set(RUBRIC_DIMENSIONS) - set(v)
        if missing:
            raise ValueError(f"judge omitted dimensions: {sorted(missing)}")
        return v

    def weighted_score(self):
        """Weighted rubric mean projected onto 0-100."""
        total = sum(self.scores[d].score * w for d, w in RUBRIC_DIMENSIONS.items())
        return (total - 1.0) / 4.0 * 100.0


class DeterministicReport(BaseModel):
    """Non-LLM measurements. These never hallucinate, so they anchor the gate."""
    word_count: int = 0
    sentence_count: int = 0
    mean_sentence_words: float = 0.0
    max_sentence_words: int = 0
    fk_grade: float = 0.0
    complex_word_ratio: float = 0.0
    readability_score: float = 0.0     # 0-100, distance from the age envelope
    banned_terms: List[str] = Field(default_factory=list)
    scary_intensity: float = 0.0       # 0-1
    ends_calmly: bool = True
    dialogue_ratio: float = 0.0
    # "Written by a machine" markers: stock phrases, over-balanced rhythm,
    # tacked-on morals. Surfaced to the reviser as concrete targets.
    ai_tells: List[str] = Field(default_factory=list)
    ai_tell_density: float = 0.0       # tells per 100 words
    human_voice_score: float = 100.0   # 0-100, higher = reads as human-written
    # Hate is a hard veto; stereotypes are reported to the reviser.
    hate_hits: List[str] = Field(default_factory=list)
    stereotype_hits: List[str] = Field(default_factory=list)
    bias_fixes: List[str] = Field(default_factory=list)
    agency_balance: float = 1.0
    passed: bool = True
    failures: List[str] = Field(default_factory=list)


class Assessment(BaseModel):
    """Aggregated judgement for one candidate story."""
    composite: float = 0.0
    llm_score: float = 0.0
    deterministic_score: float = 0.0
    dimension_medians: Dict[str, float] = Field(default_factory=dict)
    dimension_spread: Dict[str, float] = Field(default_factory=dict)
    agreement: float = 1.0             # 1 - normalised inter-sample variance
    safety_violation: bool = False
    must_fix: List[str] = Field(default_factory=list)
    strengths: List[str] = Field(default_factory=list)
    deterministic: DeterministicReport = Field(default_factory=DeterministicReport)
    n_samples: int = 0
    passed: bool = False
    fail_reasons: List[str] = Field(default_factory=list)


class StoryCandidate(BaseModel):
    revision: int = 0
    title: str = ""
    text: str = ""
    assessment: Optional[Assessment] = None
    source: str = "draft"              # draft | revision | regeneration | fallback

# Result & telemetry

class RunStatus(str, Enum):
    OK = "ok"
    OK_DEGRADED = "ok_degraded"        # shipped, but below target quality
    REFUSED = "refused"                # blocked by input guardrail
    FALLBACK = "fallback"              # safe canned story served
    ERROR = "error"


class UsageLedger(BaseModel):
    calls: int = 0
    cached_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    usd: float = 0.0
    by_stage: Dict[str, int] = Field(default_factory=dict)


class StoryResult(BaseModel):
    run_id: str = Field(default_factory=lambda: new_id("run"))
    status: RunStatus = RunStatus.OK
    title: str = ""
    story: str = ""
    message: str = ""                  # user-facing note (refusals, degradation)
    brief: Optional[StoryBrief] = None
    plan: Optional[StoryPlan] = None
    assessment: Optional[Assessment] = None
    revisions_used: int = 0
    candidates: List[StoryCandidate] = Field(default_factory=list)
    usage: UsageLedger = Field(default_factory=UsageLedger)
    latency_s: float = 0.0
    started_at: float = Field(default_factory=time.time)
    warnings: List[str] = Field(default_factory=list)

    def summary(self):
        a = self.assessment
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "title": self.title,
            "composite": round(a.composite, 1) if a else None,
            "agreement": round(a.agreement, 3) if a else None,
            "revisions": self.revisions_used,
            "words": a.deterministic.word_count if a else None,
            "fk_grade": round(a.deterministic.fk_grade, 2) if a else None,
            "latency_s": round(self.latency_s, 2),
            "usd": round(self.usage.usd, 5),
            "calls": self.usage.calls,
        }
