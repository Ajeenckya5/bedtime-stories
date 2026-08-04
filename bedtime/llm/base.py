"""Provider protocol + JSON extraction helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Type, TypeVar

from pydantic import BaseModel, ValidationError

from ..errors import StructuredOutputError

T = TypeVar("T", bound=BaseModel)


@dataclass
class LLMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
    finish_reason: str = "stop"
    cached: bool = False
    latency_s: float = 0.0
    attempts: int = 1
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass
class ChatRequest:
    """A single model call, tagged with the pipeline stage that issued it.

    `stage` is what makes per-stage cost/latency attribution possible in the
    dashboard - you can see that the judge is 40% of your spend.
    """
    system: str
    user: str
    stage: str = "generic"
    temperature: float = 0.7
    max_tokens: int = 800
    json_mode: bool = False
    seed: Optional[int] = None

    def messages(self):
        msgs: List[Dict[str, str]] = []
        if self.system:
            msgs.append({"role": "system", "content": self.system})
        msgs.append({"role": "user", "content": self.user})
        return msgs

    def cache_key_material(self):
        return json.dumps(
            {
                "s": self.system,
                "u": self.user,
                "t": round(self.temperature, 3),
                "m": self.max_tokens,
                "j": self.json_mode,
                "seed": self.seed,
            },
            sort_keys=True,
        )


class LLMProvider(Protocol):
    name: str

    def chat(self, request: ChatRequest) -> LLMResponse: ...

    def moderate(self, text: str) -> Dict[str, Any]: ...

# Structured output handling

_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)
_SMART_QUOTES = {"“": '"', "”": '"', "‘": "'", "’": "'"}
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


def extract_json(text: str) -> Any:
    """Pull a JSON value out of a chat completion."""
    if not text or not text.strip():
        raise StructuredOutputError("empty model response")

    candidates: List[str] = []
    stripped = text.strip()
    candidates.append(stripped)

    fenced = _FENCE_RE.findall(text)
    candidates.extend(block.strip() for block in fenced)

    # Balanced-brace scan: tolerant of prose before/after the object.
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        if start == -1:
            continue
        depth, in_str, escape = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if escape:
                escape = False
                continue
            if ch == "\\":
                escape = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == opener:
                depth += 1
            elif ch == closer:
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break

    for candidate in candidates:
        for repaired in (candidate, _repair(candidate)):
            try:
                return json.loads(repaired)
            except (json.JSONDecodeError, TypeError):
                continue

    raise StructuredOutputError(f"no parsable JSON in response: {text[:200]!r}")


def _repair(text: str):
    for bad, good in _SMART_QUOTES.items():
        text = text.replace(bad, good)
    text = _TRAILING_COMMA_RE.sub(r"\1", text)
    text = text.replace("\n", " ") if text.count('"') % 2 == 0 else text
    return text


def parse_model(text: str, model_cls: Type[T]) -> T:
    data = extract_json(text)
    if not isinstance(data, dict):
        # extract_json is tolerant by design (see input_guard's own isinstance
        # check) and can latch onto a stray array - e.g. a `must_fix` list -
        # when the real object got truncated. Fail with a message that points
        # at the actual problem instead of pydantic's opaque "not a dict".
        raise StructuredOutputError(
            f"{model_cls.__name__}: expected a JSON object, got "
            f"{type(data).__name__} (response likely truncated or malformed)"
        )
    try:
        return model_cls.model_validate(data)
    except ValidationError as exc:
        raise StructuredOutputError(f"{model_cls.__name__} validation failed: {exc}") from exc


def repair_prompt(original_instruction: str, bad_output: str, error: str) -> str:
    return (
        "Your previous reply could not be parsed as valid JSON.\n\n"
        f"Parser error: {error}\n\n"
        f"Your previous reply was:\n<<<\n{bad_output[:2500]}\n>>>\n\n"
        "Reply again with the SAME content, but as a single valid JSON object.\n"
        "Rules: no markdown fences, no commentary before or after, no trailing "
        "commas, all strings double-quoted.\n\n"
        f"Required shape:\n{original_instruction}"
    )
