"""Bedtime Story Engine - entry point.

    python main.py                                  interactive
    python main.py "a story about a shy dragon"     one-shot
    python main.py --mock "..."                     offline, no API key needed

`call_model` below is kept from the original skeleton so the assignment's
interface still works, but it now routes through the real provider stack
(retries, rate limiting, circuit breaker, budget cap) instead of calling the
SDK directly. Model is still gpt-3.5-turbo - see bedtime/config.py:MODEL.


What I'd build next, given another two hours
--------------------------------------------
1. Replace the fixed accept threshold with a per-category one. The calibration
   run already shows silly_humor scores ~4 points lower than bedtime_lullaby on
   the same rubric, so one global cut-off is quietly stricter on comedy.

2. Pairwise judging for the revision decision. Absolute 1-5 scoring is noisy
   (mean inter-sample spread is ~0.6 on a 4-point range). Asking "is A or B
   better" is a much easier question for gpt-3.5 and would let me cut
   judge_samples from 3 to 2 and spend the saving on an extra revision.

3. A real human-label set. Right now the golden set is my own labels, which
   makes the calibration numbers internally consistent but not externally
   valid. 100 stories rated by 3 parents would let me report actual judge-human
   correlation instead of judge-heuristic correlation.

4. Streaming. First token in ~1s instead of a full story in ~25s changes how
   the product feels completely. The judge would run on the completed text and
   revisions would be offered as "want me to polish it?" rather than blocking.

5. Cache the plan, not just the prompt. Two requests for "a story about a cat
   named Bob" produce near-identical beat sheets; reusing the plan and
   re-drafting only the prose would cut cost per story by about a third.
"""

from __future__ import annotations

import os
import sys

from bedtime.cli import main as cli_main
from bedtime.config import MODEL, get_settings
from bedtime.llm.base import ChatRequest
from bedtime.orchestrator import build_provider


def call_model(prompt: str, max_tokens: int = 3000, temperature: float = 0.1) -> str:
    """Original skeleton signature, kept working.

    Now goes through the provider layer, so it gets retries with backoff,
    rate limiting, the circuit breaker and cost accounting for free.
    """
    provider = build_provider(get_settings())
    return provider.chat(
        ChatRequest(system="", user=prompt, stage="raw",
                    temperature=temperature, max_tokens=max_tokens)
    ).text


example_requests = "A story about a girl named Alice and her best friend Bob, who happens to be a cat."


if __name__ == "__main__":
    sys.exit(cli_main())
