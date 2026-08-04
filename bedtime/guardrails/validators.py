"""Optional third-party validator layer (Guardrails AI, NeMo).

Off unless BEDTIME_VALIDATORS is set. Adapters import lazily and self-disable
if the package isn't installed.
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Protocol

from ..observability.metrics import METRICS
from ..observability.tracing import LOG


class Severity(str, Enum):
    BLOCK = "block"
    SANITIZE = "sanitize"
    WARN = "warn"
    PASS = "pass"


@dataclass
class ValidatorResult:
    name: str
    severity: Severity = Severity.PASS
    reasons: List[str] = field(default_factory=list)
    fixed_value: Optional[str] = None
    scores: Dict[str, float] = field(default_factory=dict)
    available: bool = True

    @property
    def blocked(self) -> bool:
        return self.severity is Severity.BLOCK


class Validator(Protocol):
    name: str
    stage: str  # "input" | "output"

    def validate(self, text: str, context: Dict[str, Any]): ...


@dataclass
class PipelineOutcome:
    text: str
    results: List[ValidatorResult] = field(default_factory=list)

    @property
    def blocked(self):
        return any(r.blocked for r in self.results)

    @property
    def block_reasons(self):
        return [f"{r.name}: {reason}" for r in self.results if r.blocked for reason in r.reasons]

    @property
    def warnings(self):
        return [f"{r.name}: {reason}" for r in self.results
                if r.severity is Severity.WARN for reason in r.reasons]


class ValidatorRegistry:
    """Ordered validator chains for input and output."""
    def __init__(self) -> None:
        self._input: List[Validator] = []
        self._output: List[Validator] = []

    def register_input(self, validator: Validator) -> None:
        self._input.append(validator)
        LOG.info("registered input validator: %s", validator.name)

    def register_output(self, validator: Validator):
        self._output.append(validator)
        LOG.info("registered output validator: %s", validator.name)

    def clear(self) -> None:
        self._input.clear()
        self._output.clear()

    def describe(self) -> Dict[str, List[str]]:
        return {"input": [v.name for v in self._input], "output": [v.name for v in self._output]}

    def run(self, stage: str, text: str, context: Optional[Dict[str, Any]] = None):
        """Run the chain for one stage. First block wins."""
        chain = self._input if stage == "input" else self._output
        outcome = PipelineOutcome(text=text)
        context = context or {}

        for validator in chain:
            try:
                result = validator.validate(outcome.text, context)
            except Exception as exc:
                # A third-party validator crashing must not take down the run.
                # Fail open, but make it loud in metrics.
                LOG.warning("validator %s raised %s", validator.name, exc)
                METRICS.inc("validator_errors_total", validator=validator.name,
                            error=type(exc).__name__)
                result = ValidatorResult(name=validator.name, severity=Severity.WARN,
                                         reasons=[f"validator error: {exc}"[:160]], available=False)

            outcome.results.append(result)
            METRICS.inc("validator_runs_total", validator=validator.name,
                        stage=stage, severity=result.severity.value)

            if result.severity is Severity.SANITIZE and result.fixed_value is not None:
                outcome.text = result.fixed_value
            if result.blocked:
                METRICS.inc("guardrail_blocks_total", guardrail=f"validator:{validator.name}",
                            reason=(result.reasons[0][:40] if result.reasons else "unspecified"))
                break  # first block wins; no point running the rest

        return outcome


REGISTRY = ValidatorRegistry()

# Adapters

class GuardrailsAIValidator:
    """Adapter for guardrails-ai (https://github.com/guardrails-ai/guardrails).

    Wraps validators from the Guardrails Hub. Install with:
        pip install guardrails-ai
        guardrails hub install hub://guardrails/toxic_language
        guardrails hub install hub://guardrails/detect_pii

    Unknown or uninstalled hub validators are skipped with a warning rather
    than raising - a missing optional dependency should degrade, not crash.
    """
    stage = "output"

    def __init__(self, validators: Optional[List[str]] = None, stage: str = "output",
                 on_fail: str = "exception") -> None:
        self.name = "guardrails_ai"
        self.stage = stage
        self._requested = validators or ["ToxicLanguage"]
        self._guard = None
        self._available = False
        self._init(on_fail)

    def _init(self, on_fail: str):
        try:
            from guardrails import Guard  # type: ignore
            from guardrails import validators as gv  # type: ignore
        except ImportError:
            LOG.info("guardrails-ai not installed - %s validator disabled", self.name)
            return

        instances = []
        for spec in self._requested:
            cls = getattr(gv, spec, None)
            if cls is None:
                LOG.warning("guardrails-ai validator %r not installed, skipping", spec)
                continue
            try:
                instances.append(cls(on_fail=on_fail))
            except Exception as exc:
                LOG.warning("could not construct guardrails-ai %s: %s", spec, exc)

        if instances:
            self._guard = Guard().use_many(*instances)
            self._available = True
            LOG.info("guardrails-ai active with: %s",
                     ", ".join(type(i).__name__ for i in instances))

    def validate(self, text: str, context: Dict[str, Any]):
        if not self._available or self._guard is None:
            return ValidatorResult(name=self.name, severity=Severity.PASS,
                                   reasons=["guardrails-ai not installed"], available=False)
        try:
            outcome = self._guard.validate(text)
        except Exception as exc:
            return ValidatorResult(name=self.name, severity=Severity.BLOCK,
                                   reasons=[f"guardrails-ai rejected the text: {exc}"[:200]])

        passed = getattr(outcome, "validation_passed", True)
        if passed:
            return ValidatorResult(name=self.name, severity=Severity.PASS)

        fixed = getattr(outcome, "validated_output", None)
        reasons = [str(getattr(outcome, "error", "validation failed"))[:200]]
        if isinstance(fixed, str) and fixed and fixed != text:
            return ValidatorResult(name=self.name, severity=Severity.SANITIZE,
                                   reasons=reasons, fixed_value=fixed)
        return ValidatorResult(name=self.name, severity=Severity.BLOCK, reasons=reasons)


class NeMoGuardrailsValidator:
    """Adapter for NVIDIA NeMo Guardrails.

    Expects a rails config directory (Colang flows + config.yml). Install with:
        pip install nemoguardrails

    Point it at your config:
        NeMoGuardrailsValidator(config_path="guardrails_config/")
    """
    stage = "input"

    def __init__(self, config_path: str = "guardrails_config", stage: str = "input"):
        self.name = "nemo_guardrails"
        self.stage = stage
        self.config_path = config_path
        self._rails = None
        self._available = False
        self._init()

    def _init(self):
        try:
            from nemoguardrails import LLMRails, RailsConfig  # type: ignore
        except ImportError:
            LOG.info("nemoguardrails not installed - %s validator disabled", self.name)
            return
        if not os.path.isdir(self.config_path):
            LOG.warning("nemo rails config not found at %s - validator disabled", self.config_path)
            return
        try:
            self._rails = LLMRails(RailsConfig.from_path(self.config_path))
            self._available = True
            LOG.info("nemo guardrails active from %s", self.config_path)
        except Exception as exc:
            LOG.warning("could not start nemo guardrails: %s", exc)

    def validate(self, text: str, context: Dict[str, Any]) -> ValidatorResult:
        if not self._available or self._rails is None:
            return ValidatorResult(name=self.name, severity=Severity.PASS,
                                   reasons=["nemoguardrails not installed"], available=False)
        try:
            response = self._rails.generate(messages=[{"role": "user", "content": text}])
            content = (response or {}).get("content", "") if isinstance(response, dict) else str(response)
        except Exception as exc:
            return ValidatorResult(name=self.name, severity=Severity.WARN,
                                   reasons=[f"nemo error: {exc}"[:160]], available=False)

        # NeMo signals a refusal in the reply text rather than structurally.
        refusal_markers = ("i can't", "i cannot", "i'm not able", "i am not able",
                           "sorry, i can", "i won't", "not allowed")
        if any(m in content.lower() for m in refusal_markers):
            return ValidatorResult(name=self.name, severity=Severity.BLOCK,
                                   reasons=[f"nemo rail refused: {content[:140]}"])
        return ValidatorResult(name=self.name, severity=Severity.PASS)


class LexiconValidator:
    """The built-in check, exposed through the same interface so the default
    stack and any third-party stack compose in one chain."""
    def __init__(self, stage: str = "output"):
        self.name = "builtin_lexicon"
        self.stage = stage

    def validate(self, text: str, context: Dict[str, Any]):
        from .lexicons import find_banned, find_dread

        banned = find_banned(text)
        dread = [d for d, _ in find_dread(text)]
        reasons = []
        if banned:
            reasons.append("banned terms: " + ", ".join(banned[:5]))
        if len(dread) >= 2:
            reasons.append("sustained dread: " + ", ".join(dread[:3]))
        severity = Severity.BLOCK if reasons else Severity.PASS
        return ValidatorResult(name=self.name, severity=severity, reasons=reasons)


def configure_from_env(registry: Optional[ValidatorRegistry] = None) -> ValidatorRegistry:
    registry = registry or REGISTRY
    requested = [v.strip().lower() for v in os.getenv("BEDTIME_VALIDATORS", "").split(",") if v.strip()]
    if not requested:
        return registry

    for name in requested:
        if name in {"guardrails_ai", "guardrails-ai", "guardrails"}:
            registry.register_output(GuardrailsAIValidator())
        elif name in {"nemo", "nemo_guardrails", "nemoguardrails"}:
            registry.register_input(NeMoGuardrailsValidator(
                config_path=os.getenv("BEDTIME_NEMO_CONFIG", "guardrails_config")))
        elif name in {"lexicon", "builtin"}:
            registry.register_output(LexiconValidator())
        else:
            LOG.warning("unknown validator %r in BEDTIME_VALIDATORS, ignoring", name)
    return registry
