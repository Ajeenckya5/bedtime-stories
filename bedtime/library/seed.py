"""Load the seed library into story memory.

    python -m bedtime.library.seed              # index all ten
    python -m bedtime.library.seed --check      # gate them, index nothing
    python -m bedtime.library.seed --force      # re-index over existing entries

Runs the stories through the system's own guardrails before indexing anything.
If a hand-written picture-book story fails the gate, the gate is wrong, and it
is better to find that here than in production.
"""

import argparse
import sys
from typing import Any, Dict, List

from ..config import get_settings
from ..guardrails.readability import readability_report
from ..memory.retriever import Retriever
from ..observability.tracing import LOG
from ..schemas import StoryBrief, StoryCategory
from .seed_stories import SEED_STORIES, balance, by_category


def check_story(entry: Dict[str, Any], band):
    rep = readability_report(entry["story"], band)
    return {
        "id": entry["id"],
        "title": entry["title"],
        "passed": rep.passed,
        "failures": rep.failures,
        "words": rep.word_count,
        "fk": rep.fk_grade,
        "mean_sentence": rep.mean_sentence_words,
        "human_voice": rep.human_voice_score,
        "readability": rep.readability_score,
        "scary": rep.scary_intensity,
        "calm": rep.ends_calmly,
        "hate": rep.hate_hits,
        "stereotypes": rep.stereotype_hits,
    }


def check_all():
    band = get_settings().age_band
    return [check_story(e, band) for e in SEED_STORIES]


def seed(force: bool = False) -> int:
    settings = get_settings()
    retriever = Retriever(settings)
    existing = {row["story_id"] for row in retriever.store.recent(limit=500)}
    indexed = 0

    for entry in SEED_STORIES:
        story_id = f"seed_{entry['id']}"
        if story_id in existing and not force:
            continue
        try:
            category = StoryCategory(entry["category"])
        except ValueError:
            category = StoryCategory.MAGIC_WONDER
        brief = StoryBrief(
            raw_request=entry["request"],
            sanitized_request=entry["request"],
            category=category,
            characters=entry["characters"],
            themes=["kindness"],
        )
        n = retriever.remember(
            story_id=story_id, run_id="seed", title=entry["title"],
            story=entry["story"], brief=brief, composite=None)
        if n:
            indexed += 1
    return indexed


def main(argv=None):
    parser = argparse.ArgumentParser(description="Seed the story library into memory.")
    parser.add_argument("--check", action="store_true", help="gate the stories, index nothing")
    parser.add_argument("--force", action="store_true", help="re-index existing entries")
    args = parser.parse_args(argv)

    results = check_all()
    failed = [r for r in results if not r["passed"]]

    print(f"{'id':<8}{'words':>6}{'FK':>6}{'sent':>6}{'read':>7}{'voice':>7}  title")
    for r in results:
        flag = "" if r["passed"] else "   <-- FAILS GATE"
        print(f"{r['id']:<8}{r['words']:>6}{r['fk']:>6.1f}{r['mean_sentence']:>6.1f}"
              f"{r['readability']:>7.1f}{r['human_voice']:>7.0f}  {r['title']}{flag}")
        for f in r["failures"]:
            print(f"          ! {f}")

    print(f"\nprotagonist balance: {balance()}")
    print(f"categories covered:  {len(by_category())}/8")

    if failed:
        print(f"\n{len(failed)} seed stories fail the gate - fix the story or the gate")
        return 1

    if args.check:
        print("\nall 10 pass the gate (nothing indexed, --check)")
        return 0

    n = seed(force=args.force)
    LOG.info("seeded %d stories into memory", n)
    print(f"\nindexed {n} stories into {get_settings().memory_db}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
