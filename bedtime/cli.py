"""Interactive command line.

Supports the feedback loop the assignment suggests: after a story is told you
can ask for changes ("make it funnier", "add a dog") and the system revises it
through the same guardrails rather than starting over.

Degrades gracefully to plain print() if `rich` is not installed.
"""

import argparse
import json
import sys
from typing import Optional

from .config import MODEL, get_settings
from .observability.metrics import METRICS
from .orchestrator import StoryOrchestrator
from .prompts import PROMPT_VERSION
from .schemas import RunStatus, StoryResult

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.table import Table

    _RICH = True
    _console = Console()
except ImportError:  # pragma: no cover
    _RICH = False
    _console = None

EXAMPLES = [
    "A story about a girl named Alice and her best friend Bob, who happens to be a cat.",
    "A shy dragon who is scared of his first day at school",
    "Why is the moon sometimes out in the daytime?",
    "Something very silly about a penguin who wants to be a chef",
]


def _print(text: str = ""):
    if _RICH:
        _console.print(text)
    else:
        print(text)


def _show_story(result: StoryResult, show_details: bool):
    if not _RICH:
        print(f"\n{result.title}\n{'=' * len(result.title)}\n")
        print(result.story)
        if result.message:
            print(f"\n[note] {result.message}")
        print(f"\n{json.dumps(result.summary())}")
        return

    border = {
        RunStatus.OK: "green",
        RunStatus.OK_DEGRADED: "yellow",
        RunStatus.REFUSED: "red",
        RunStatus.FALLBACK: "yellow",
        RunStatus.ERROR: "red",
    }.get(result.status, "blue")

    _console.print()
    _console.print(Panel(Markdown(result.story), title=f"[bold]{result.title}[/bold]",
                         border_style=border, padding=(1, 3)))
    if result.message:
        _console.print(f"[italic dim]{result.message}[/italic dim]")

    if show_details and result.assessment:
        a = result.assessment
        table = Table(title="Quality assessment", show_header=True, header_style="bold")
        table.add_column("Dimension")
        table.add_column("Median", justify="right")
        table.add_column("Spread", justify="right")
        for dim, score in sorted(a.dimension_medians.items(), key=lambda kv: kv[1]):
            spread = a.dimension_spread.get(dim, 0.0)
            colour = "green" if score >= 4 else ("yellow" if score >= 3 else "red")
            table.add_row(dim.replace("_", " "), f"[{colour}]{score:.1f}[/{colour}]", f"{spread:.1f}")
        _console.print(table)

        d = a.deterministic
        _console.print(
            f"[dim]composite [bold]{a.composite:.1f}[/bold]/100  "
            f"(llm {a.llm_score:.1f} · deterministic {a.deterministic_score:.1f})   "
            f"judge agreement {a.agreement:.0%} over {a.n_samples} samples[/dim]"
        )
        _console.print(
            f"[dim]{d.word_count} words · FK grade {d.fk_grade:.1f} · "
            f"mean sentence {d.mean_sentence_words:.1f}w · "
            f"scary {d.scary_intensity:.2f} · ends calmly: {d.ends_calmly}[/dim]"
        )
        if a.fail_reasons:
            _console.print(f"[yellow]gate notes: {'; '.join(a.fail_reasons[:3])}[/yellow]")
        _console.print(
            f"[dim]{result.revisions_used} revision(s) · {result.usage.calls} model calls · "
            f"${result.usage.usd:.4f} · {result.latency_s:.1f}s · run {result.run_id}[/dim]"
        )


def _banner(settings):
    mode = "offline mock" if settings.provider == "mock" else MODEL
    if _RICH:
        _console.print(Panel(
            "[bold]Bedtime Story Engine[/bold]\n"
            f"[dim]model {mode} · prompts {PROMPT_VERSION} · "
            f"threshold {settings.gate.accept_threshold:.0f} · "
            f"{settings.gate.judge_samples} judge samples[/dim]\n\n"
            "Ask for any story. After it's told you can request changes,\n"
            "or type [bold]play[/bold] to hear it aloud, [bold]new[/bold] for another,\n"
            "[bold]why[/bold] for the scores, [bold]quit[/bold] to leave.",
            border_style="blue", padding=(1, 3)))
    else:
        print(f"Bedtime Story Engine ({mode})")


def narrate_and_play(result) -> None:
    """Render the story to audio and play it."""
    if not result.story:
        return
    from .narration.narrator import Narrator

    settings = get_settings()
    if not settings.tts_enabled:
        _print("Narration is off (BEDTIME_TTS=false).")
        return

    narrator = Narrator(settings)
    _print("[dim]narrating…[/dim]" if _RICH else "narrating...")
    narration = narrator.narrate(result.story, result.title)

    if not narration.ok:
        _print(f"[yellow]Couldn't narrate: {narration.error}[/yellow]"
               if _RICH else f"Couldn't narrate: {narration.error}")
        return

    tag = "cached" if narration.cached else f"{narration.engine}/{narration.voice}"
    _print(f"[dim]audio ready ({tag}, ~{narration.duration_estimate_s:.0f}s) "
           f"{narration.audio_path}[/dim]" if _RICH
           else f"audio: {narration.audio_path}")
    if not narrator.play(narration):
        _print("[dim](no audio player found - open the file above)[/dim]"
               if _RICH else "(open the file above to listen)")


def run_once(request: str, as_json: bool = False, details: bool = True):
    result = StoryOrchestrator().tell(request)
    if as_json:
        print(json.dumps(result.model_dump(mode="json"), indent=2, default=str))
    else:
        _show_story(result, details)
    return result


def interactive(details: bool = True) -> None:
    settings = get_settings()
    _banner(settings)
    orchestrator = StoryOrchestrator(settings=settings)
    if settings.provider == "mock":
        _print("[yellow]No OPENAI_API_KEY found - running the offline mock provider.[/yellow]"
               if _RICH else "No OPENAI_API_KEY - offline mock provider.")
    _print(f"[dim]Try: {EXAMPLES[0]}[/dim]" if _RICH else f"Try: {EXAMPLES[0]}")

    result: Optional[StoryResult] = None
    while True:
        try:
            prompt = "\nWhat kind of story do you want to hear? " if result is None else \
                     "\nAny changes? (or 'play' / 'new' / 'why' / 'quit') "
            user_input = input(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            _print("\nGoodnight!")
            return

        if not user_input:
            continue
        low = user_input.lower()
        if low in {"quit", "exit", "q", "bye"}:
            _print("Goodnight!")
            return
        if low in {"new", "another", "again"}:
            result = None
            continue
        if low in {"why", "scores", "detail", "details"}:
            if result:
                _show_story(result, show_details=True)
            continue
        if low in {"play", "read", "audio", "listen"}:
            if result:
                narrate_and_play(result)
            continue
        if low in {"metrics", "stats"}:
            print(json.dumps(METRICS.snapshot(), indent=2, default=str))
            continue

        try:
            if result is None or result.status in {RunStatus.REFUSED, RunStatus.ERROR}:
                result = orchestrator.tell(user_input)
            else:
                result = orchestrator.refine(result, user_input)
            _show_story(result, details)
        except KeyboardInterrupt:
            _print("\n(cancelled)")
        except Exception as exc:  # pragma: no cover
            _print(f"[red]Sorry - {type(exc).__name__}: {exc}[/red]" if _RICH else f"Error: {exc}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="bedtime",
        description="Generate a judged, guardrailed bedtime story for ages 5-10.",
    )
    parser.add_argument("request", nargs="*", help="story request; omit for interactive mode")
    parser.add_argument("--json", action="store_true", help="emit the full result as JSON")
    parser.add_argument("--quiet", action="store_true", help="hide the quality breakdown")
    parser.add_argument("--mock", action="store_true", help="force the offline mock provider")
    parser.add_argument("--audio", action="store_true",
                        help="narrate the story aloud after printing it")
    parser.add_argument("--voice", help="TTS voice (nova, shimmer, alloy, fable, echo, onyx)")
    parser.add_argument("--threshold", type=float, help="override the accept threshold")
    parser.add_argument("--revisions", type=int, help="override max revision cycles")
    parser.add_argument("--samples", type=int, help="override judge samples")
    args = parser.parse_args(argv)

    import os

    if args.mock:
        os.environ["BEDTIME_PROVIDER"] = "mock"
    if args.voice:
        os.environ["BEDTIME_TTS_VOICE"] = args.voice
    if args.threshold is not None:
        os.environ["BEDTIME_ACCEPT_THRESHOLD"] = str(args.threshold)
    if args.revisions is not None:
        os.environ["BEDTIME_MAX_REVISIONS"] = str(args.revisions)
    if args.samples is not None:
        os.environ["BEDTIME_JUDGE_SAMPLES"] = str(args.samples)
    get_settings(refresh=True)

    if args.request:
        result = run_once(" ".join(args.request), as_json=args.json, details=not args.quiet)
        if args.audio:
            narrate_and_play(result)
        return 0 if result.status in {RunStatus.OK, RunStatus.OK_DEGRADED} else 1
    interactive(details=not args.quiet)
    return 0


if __name__ == "__main__":
    sys.exit(main())
