"""Central configuration.

Every tunable in the system lives here so that behaviour is auditable and
reproducible: a run's trace records the exact Settings snapshot that produced it.

Values are read from the environment (optionally via a local `.env` file).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict

MODEL: str = "gpt-3.5-turbo"
MODEL_SUNSET = "2026-10-23"

MIGRATION = """
Changing MODEL means redoing three things, in this order:

1. Re-run `python -m bedtime.evaluation.calibrate`. The 82 accept threshold was
   derived from gpt-3.5-turbo's score distribution. A stronger model scores
   higher across the board, so the old threshold stops discriminating - almost
   everything passes first try and the judge loop becomes decorative.
2. Re-tune the 75/25 llm/deterministic blend in QualityGate. A better judge
   deserves more weight; the deterministic anchor exists partly to compensate
   for gpt-3.5 being miscalibrated.
3. Re-check the prompts. A lot of what is in prompts.py exists to work around
   gpt-3.5 specifically - the JSON repair path, the heavy anti-stock-phrase
   list, the "trust these measurements over your impression" instruction. A
   newer model needs less hand-holding and the extra scaffolding may hurt.

Update DEFAULT_*_USD_PER_MTOK too, or the budget guard will be wrong.
"""
# Published prices (USD per 1M tokens) for gpt-3.5-turbo-0125. Used for the
# cost ledger and budget guard. Override via env if OpenAI repricing occurs.
DEFAULT_PROMPT_USD_PER_MTOK = 0.50
DEFAULT_COMPLETION_USD_PER_MTOK = 1.00
# Checked Aug 2026. Override with BEDTIME_PROMPT_PRICE / BEDTIME_COMPLETION_PRICE
# if OpenAI reprices - the cost ledger and budget guard both read from here.

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _env_str(key: str, default: str):
    return os.getenv(key, default)


def _env_int(key: str, default: int):
    try:
        return int(os.getenv(key, default))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _env_float(key: str, default: float) -> float:
    try:
        return float(os.getenv(key, default))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _env_bool(key: str, default: bool):
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class QualityGate:
    """Thresholds that decide whether a story ships.

    Defaults are the calibrated values produced by
    `python -m bedtime.evaluation.calibrate` against the golden set in
    `bedtime/evaluation/golden_set.json`. Re-run calibration after any prompt
    change; see docs/CALIBRATION_REPORT.md.
    """
    # Composite score (0-100) a story must reach to be released.
    accept_threshold: float = 82.0
    # Below this a story is considered unsalvageable; we stop revising and
    # regenerate from scratch instead of polishing a bad draft.
    regenerate_below: float = 55.0
    # Maximum judge -> revise cycles. Each cycle costs 2 model calls.
    max_revisions: int = 3
    # A revision must beat the previous best by this margin to be adopted.
    # Prevents "revision thrash" where scores oscillate inside judge noise.
    min_improvement_delta: float = 1.5
    # Number of independent judge samples per evaluation (self-consistency).
    # 1 = cheap/noisy, 3 = recommended, 5 = research-grade.
    judge_samples: int = 3
    # Any rubric dimension below this is an automatic fail regardless of the
    # composite score. Stops a great-prose / unsafe-content story from passing.
    min_dimension_score: float = 3.0
    # Blend of LLM rubric vs deterministic (readability/lexicon) signal.
    # The deterministic share anchors the notoriously miscalibrated LLM judge.
    llm_weight: float = 0.75
    deterministic_weight: float = 0.25


@dataclass(frozen=True)
class AgeBand:
    """Target readability envelope for the 5-10 age band.

    Sources: Flesch-Kincaid grade level targets for early-elementary read-aloud
    text; sentence-length norms from children's trade fiction.
    """
    min_age: int = 5
    max_age: int = 10
    # Floor was 1.5 until calibration showed it punishing genuinely good
    # picture-book prose - real early-reader text often measures FK 1.0-1.5.
    target_fk_grade: float = 2.8
    fk_grade_floor: float = 0.8
    fk_grade_ceiling: float = 5.0
    target_sentence_words: float = 11.0
    sentence_words_floor: float = 7.0
    sentence_words_ceiling: float = 16.0
    # Share of words with 3+ syllables. Above this the text starts to feel
    # academic rather than read-aloud.
    max_complex_word_ratio: float = 0.09
    max_sentence_words_hard: int = 28


@dataclass(frozen=True)
class Settings:
    api_key: str = field(default="", repr=False)
    base_url: str = ""
    provider: str = "openai"
    request_timeout_s: float = 45.0
    max_retries: int = 4
    retry_base_delay_s: float = 0.75
    retry_max_delay_s: float = 12.0

    # resilience
    rate_limit_rpm: int = 60
    circuit_fail_threshold: int = 5
    circuit_reset_s: float = 30.0
    max_usd_per_run: float = 0.25
    max_usd_per_day: float = 25.00
    enable_cache: bool = True

    # safety
    # The OpenAI Moderation endpoint is a non-generative classifier, not a chat
    # model: enabling it does not violate the "do not change the model" rule.
    # Set BEDTIME_USE_MODERATION_API=false for a purely gpt-3.5-turbo system.
    use_moderation_api: bool = True
    moderation_model: str = "omni-moderation-latest"
    max_input_chars: int = 800
    strict_safety: bool = True        # unresolved safety doubt => refuse/fallback

    # --- generation ---------------------------------------------------------
    target_words_min: int = 550
    target_words_max: int = 900
    planner_temperature: float = 0.7
    storyteller_temperature: float = 0.85
    reviser_temperature: float = 0.55
    judge_temperature: float = 0.2
    classifier_temperature: float = 0.0
    max_tokens_story: int = 1600
    max_tokens_plan: int = 700
    max_tokens_judge: int = 900
    max_tokens_small: int = 350

    # --- memory (story continuity) ------------------------------------------
    # Retrieval over past stories so "another one about Bramble" keeps Bramble
    # consistent. Embeddings use text-embedding-3-small - a non-generative
    # encoder. Story generation and judging remain gpt-3.5-turbo only.
    memory_enabled: bool = True
    memory_db: Path = PROJECT_ROOT / "data" / "memory.sqlite3"
    use_embeddings: bool = True
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    memory_chunk_words: int = 120
    memory_chunk_overlap: int = 30
    memory_top_k: int = 4
    memory_min_similarity: float = 0.38
    memory_context_words: int = 450   # hard cap on continuity injected into prompts

    # narration. Separate opt-in call, not a pipeline stage - it costs money and
    # a voice outage must never stop a story going out as text.
    tts_enabled: bool = True
    tts_engine: str = "auto"          # auto | openai | system
    tts_model: str = "gpt-4o-mini-tts"
    tts_voice: str = "nova"           # warmest of the OpenAI voices
    tts_system_voice: str = ""        # e.g. "Daniel" on macOS
    tts_speed: float = 0.92           # under 1.0 - default pace is brisk for a child
    audio_dir: Path = PROJECT_ROOT / "audio"

    cache_db: Path = PROJECT_ROOT / "data" / "cache.sqlite3"
    cache_ttl_days: float = 14.0
    plan_cache_enabled: bool = True
    # Off by default: the failure mode is a child hearing the same story twice.
    story_cache_enabled: bool = False

    trace_dir: Path = PROJECT_ROOT / "traces"
    log_level: str = "INFO"
    redact_story_text_in_traces: bool = False

    # --- api ----------------------------------------------------------------
    api_rate_limit_rpm: int = 20
    api_key_header: str = "x-api-key"
    service_api_keys: tuple = ()      # empty => auth disabled (local dev)

    gate: QualityGate = field(default_factory=QualityGate)
    age_band: AgeBand = field(default_factory=AgeBand)

    prompt_usd_per_mtok: float = DEFAULT_PROMPT_USD_PER_MTOK
    completion_usd_per_mtok: float = DEFAULT_COMPLETION_USD_PER_MTOK

    @classmethod
    def from_env(cls, env_file: Path | None = None):
        _load_dotenv(env_file or (PROJECT_ROOT / ".env"))
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        provider = _env_str("BEDTIME_PROVIDER", "openai" if api_key else "mock")
        raw_keys = _env_str("BEDTIME_SERVICE_API_KEYS", "").strip()
        service_keys = tuple(k.strip() for k in raw_keys.split(",") if k.strip())

        gate = QualityGate(
            accept_threshold=_env_float("BEDTIME_ACCEPT_THRESHOLD", 82.0),
            regenerate_below=_env_float("BEDTIME_REGENERATE_BELOW", 55.0),
            max_revisions=_env_int("BEDTIME_MAX_REVISIONS", 3),
            judge_samples=_env_int("BEDTIME_JUDGE_SAMPLES", 3),
            min_dimension_score=_env_float("BEDTIME_MIN_DIMENSION", 3.0),
        )
        return cls(
            api_key=api_key,
            base_url=_env_str("OPENAI_BASE_URL", ""),
            provider=provider,
            request_timeout_s=_env_float("BEDTIME_TIMEOUT_S", 45.0),
            max_retries=_env_int("BEDTIME_MAX_RETRIES", 4),
            rate_limit_rpm=_env_int("BEDTIME_RATE_LIMIT_RPM", 60),
            max_usd_per_run=_env_float("BEDTIME_MAX_USD_PER_RUN", 0.25),
            max_usd_per_day=_env_float("BEDTIME_MAX_USD_PER_DAY", 25.00),
            enable_cache=_env_bool("BEDTIME_ENABLE_CACHE", True),
            use_moderation_api=_env_bool("BEDTIME_USE_MODERATION_API", True),
            strict_safety=_env_bool("BEDTIME_STRICT_SAFETY", True),
            target_words_min=_env_int("BEDTIME_WORDS_MIN", 550),
            target_words_max=_env_int("BEDTIME_WORDS_MAX", 900),
            memory_enabled=_env_bool("BEDTIME_MEMORY", True),
            memory_db=Path(_env_str("BEDTIME_MEMORY_DB", str(PROJECT_ROOT / "data" / "memory.sqlite3"))),
            use_embeddings=_env_bool("BEDTIME_USE_EMBEDDINGS", True),
            embedding_model=_env_str("BEDTIME_EMBEDDING_MODEL", "text-embedding-3-small"),
            memory_top_k=_env_int("BEDTIME_MEMORY_TOP_K", 4),
            memory_min_similarity=_env_float("BEDTIME_MEMORY_MIN_SIM", 0.38),
            memory_context_words=_env_int("BEDTIME_MEMORY_CONTEXT_WORDS", 450),
            memory_chunk_words=_env_int("BEDTIME_CHUNK_WORDS", 120),
            memory_chunk_overlap=_env_int("BEDTIME_CHUNK_OVERLAP", 30),
            cache_db=Path(_env_str("BEDTIME_CACHE_DB", str(PROJECT_ROOT / "data" / "cache.sqlite3"))),
            cache_ttl_days=_env_float("BEDTIME_CACHE_TTL_DAYS", 14.0),
            plan_cache_enabled=_env_bool("BEDTIME_PLAN_CACHE", True),
            story_cache_enabled=_env_bool("BEDTIME_STORY_CACHE", False),
            tts_enabled=_env_bool("BEDTIME_TTS", True),
            tts_engine=_env_str("BEDTIME_TTS_ENGINE", "auto"),
            tts_model=_env_str("BEDTIME_TTS_MODEL", "gpt-4o-mini-tts"),
            tts_voice=_env_str("BEDTIME_TTS_VOICE", "nova"),
            tts_system_voice=_env_str("BEDTIME_TTS_SYSTEM_VOICE", ""),
            tts_speed=_env_float("BEDTIME_TTS_SPEED", 0.92),
            audio_dir=Path(_env_str("BEDTIME_AUDIO_DIR", str(PROJECT_ROOT / "audio"))),
            trace_dir=Path(_env_str("BEDTIME_TRACE_DIR", str(PROJECT_ROOT / "traces"))),
            log_level=_env_str("BEDTIME_LOG_LEVEL", "INFO"),
            redact_story_text_in_traces=_env_bool("BEDTIME_REDACT_TRACES", False),
            api_rate_limit_rpm=_env_int("BEDTIME_API_RATE_LIMIT_RPM", 20),
            service_api_keys=service_keys,
            prompt_usd_per_mtok=_env_float("BEDTIME_PROMPT_PRICE", DEFAULT_PROMPT_USD_PER_MTOK),
            completion_usd_per_mtok=_env_float("BEDTIME_COMPLETION_PRICE", DEFAULT_COMPLETION_USD_PER_MTOK),
            gate=gate,
        )

    def redacted(self):
        """Config snapshot safe for logs, traces and API responses."""
        data = asdict(self)
        data.pop("api_key", None)
        data.pop("service_api_keys", None)
        data["trace_dir"] = str(self.trace_dir)
        data["memory_db"] = str(self.memory_db)
        data["cache_db"] = str(self.cache_db)
        data["audio_dir"] = str(self.audio_dir)
        data["model"] = MODEL
        data["api_key_present"] = bool(self.api_key)
        return data


_SETTINGS: Settings | None = None


def get_settings(refresh: bool = False):
    global _SETTINGS
    if _SETTINGS is None or refresh:
        _SETTINGS = Settings.from_env()
    return _SETTINGS
