"""Shared agent base.

structured_call() parses into a pydantic model and, on failure, does one repair
call showing the model its own broken output. One retry is enough in practice.
"""

from typing import Optional, Tuple, Type, TypeVar

from pydantic import BaseModel

from ..config import Settings
from ..errors import StructuredOutputError
from ..llm.base import ChatRequest, LLMProvider, parse_model, repair_prompt
from ..observability.metrics import METRICS

T = TypeVar("T", bound=BaseModel)


class Agent:
    """Base for every pipeline stage. Holds the provider, settings and trace."""
    stage = "generic"

    def __init__(self, provider: LLMProvider, settings: Settings, trace=None):
        self.provider = provider
        self.settings = settings
        self.trace = trace

    # -- plain text ---------------------------------------------------------
    def text_call(
        self,
        system: str,
        user: str,
        *,
        temperature: float,
        max_tokens: int,
        seed: Optional[int] = None,
    ) -> str:
        """Plain text completion."""
        response = self.provider.chat(
            ChatRequest(
                system=system,
                user=user,
                stage=self.stage,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
            )
        )
        if response.finish_reason == "length":
            METRICS.inc("llm_truncated_total", stage=self.stage)
            if self.trace is not None:
                self.trace.event("response_truncated", stage=self.stage,
                                 tokens=response.completion_tokens)
        return response.text.strip()

    # -- structured ---------------------------------------------------------
    def structured_call(
        self,
        system: str,
        user: str,
        model_cls: Type[T],
        *,
        temperature: float,
        max_tokens: int,
        schema_hint: str = "",
        seed: Optional[int] = None,
    ) -> Tuple[T, bool]:
        response = self.provider.chat(
            ChatRequest(
                system=system,
                user=user,
                stage=self.stage,
                temperature=temperature,
                max_tokens=max_tokens,
                json_mode=True,
                seed=seed,
            )
        )
        try:
            return parse_model(response.text, model_cls), False
        except StructuredOutputError as exc:
            # Python unbinds `exc` at the end of the except block, so keep the
            # message in a normal local before falling through to the repair.
            first_error = str(exc)
            METRICS.inc("structured_repairs_total", stage=self.stage)
            if self.trace is not None:
                self.trace.event("structured_repair", stage=self.stage, error=first_error[:160])

        repaired = self.provider.chat(
            ChatRequest(
                system=system,
                user=repair_prompt(schema_hint or model_cls.__name__, response.text, first_error),
                stage=f"{self.stage}_repair",
                temperature=0.0,
                max_tokens=max_tokens,
                json_mode=True,
            )
        )
        try:
            return parse_model(repaired.text, model_cls), True
        except StructuredOutputError as second_error:
            METRICS.inc("structured_failures_total", stage=self.stage)
            raise StructuredOutputError(
                f"{self.stage}: could not parse {model_cls.__name__} after repair "
                f"({second_error})"
            ) from second_error


def strip_title(text: str) -> Tuple[str, str]:
    import re

    if not text:
        return "", ""
    lines = text.strip().splitlines()
    title = ""
    body_start = 0
    for i, line in enumerate(lines[:3]):
        m = re.match(r"^\s*[*#\s]*(?:title)\s*[:\-–]\s*(.+?)\s*[*#]*\s*$", line, re.I)
        if m:
            title = m.group(1).strip().strip('"').strip("*").strip()
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    if not title:
        # No TITLE line: treat a short, punctuation-free first line as the title.
        first = lines[0].strip().strip('"').strip("*")
        if 0 < len(first.split()) <= 9 and not first.endswith((".", "!", "?", ",")):
            title, body = first, "\n".join(lines[1:]).strip()
    return title, body or text.strip()
