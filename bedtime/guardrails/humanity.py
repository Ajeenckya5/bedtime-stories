"""Detects "a model wrote this": stock phrases, uniform rhythm, stated morals.

Feeds the offending phrases to the reviser by name.
"""

from __future__ import annotations

import re
import statistics
from collections import Counter
from typing import Dict, List, Tuple

# Weighted: some are merely common, some are unmistakable.
STOCK_PHRASES: Dict[str, float] = {
    # openings
    "once upon a time, in a land": 1.0,
    "in a world where": 1.0,
    "nestled in": 0.8, "nestled among": 0.8, "nestled between": 0.8,
    "in a quaint little": 0.9, "in a cozy little": 0.7,
    "there once lived": 0.6,
    "little did (?:he|she|they|.{2,12}) know": 1.0,
    # transitions
    "as the sun (?:dipped|sank|set|began to set)": 1.0,
    "as the sun rose": 0.7,
    "as the (?:days|weeks|years) (?:went by|passed)": 0.7,
    "from that day (?:on|forward|forth)": 1.0,
    "and so it was that": 0.8,
    "with a twinkle in (?:his|her|their|its) eye": 0.9,
    "little by little": 0.5,
    "before (?:he|she|they) knew it": 0.7,
    # emotional filler
    "(?:heart|heart[s]?) (?:swell|swelled|swelling|soared|soar)": 1.0,
    "filled with (?:joy|wonder|warmth|happiness|delight)": 0.9,
    "a sense of (?:wonder|belonging|peace|calm|accomplishment)": 1.0,
    "warm(?:th)? (?:spread|washed over|flooded)": 0.8,
    "couldn't help but (?:smile|giggle|laugh)": 0.9,
    "eyes (?:sparkled|twinkled|lit up) with": 0.8,
    "beamed with pride": 0.9,
    # moralising
    "and (?:he|she|they) learned that": 1.0,
    "the (?:most important|greatest) lesson": 1.0,
    "(?:realized|realised) that (?:true|real) (?:friendship|courage|magic|happiness)": 1.0,
    "reminding (?:everyone|them|us) that": 0.9,
    "a reminder that": 0.8,
    "no matter how (?:small|big|different)": 0.8,
    "always (?:believe in|remember to)": 0.8,
    # closings
    "lived happily ever after": 0.7,
    "the end\\.?$": 0.6,
    "drifted off (?:to|into) (?:a )?(?:peaceful|sweet|gentle) (?:sleep|slumber|dreams)": 0.9,
    "dreams (?:as sweet as|filled with)": 0.8,
    "and (?:so|thus), (?:with|as)": 0.6,
    # generic scenery
    "shimmer(?:ing|ed) in the (?:moon|sun)light": 0.9,
    "bathed in (?:golden|silver|moon)": 0.9,
    "a symphony of": 1.0,
    "dancing (?:in|on) the (?:breeze|wind)": 0.8,
    "whisper(?:ed|ing) (?:secrets|softly) (?:to|in)": 0.8,
    "as if by magic": 0.7,
    "little (?:did|by)": 0.4,
    # register slips (adult vocabulary in a 5-10 story)
    "embark(?:ed)? on (?:a|an|this) (?:journey|adventure|quest)": 1.0,
    "unbeknownst to": 1.0,
    "myriad": 0.8, "plethora": 1.0, "tapestry": 0.9, "testament to": 1.0,
    "delve": 0.8, "navigate the": 0.7, "foster(?:ing)? a": 0.8,
    "in the realm of": 0.9, "beacon of": 0.9, "vibrant": 0.5, "bustling": 0.6,
    "whimsical": 0.7, "enchanting": 0.6, "resilience": 0.8,
}

_ADVERB_TAG = re.compile(
    r'"\s*,?\s*(?:said|replied|asked|whispered|exclaimed|shouted|murmured)\s+\w+\s+\w+ly\b', re.I)
_TRICOLON = re.compile(r"\b\w+,\s+\w+,\s+and\s+\w+\b")
_EM_DASH = re.compile(r"—|--")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+|\n{2,}")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")

_MORAL_MARKERS = (
    "learned that", "lesson", "realized", "realised", "taught", "moral",
    "reminder", "important thing", "always remember", "from that day",
)


def find_stock_phrases(text: str):
    low = text.lower()
    hits: List[Tuple[str, float]] = []
    for pattern, weight in STOCK_PHRASES.items():
        m = re.search(pattern, low, re.M)
        if m:
            hits.append((m.group(0).strip(), weight))
    return sorted(hits, key=lambda kv: -kv[1])


# TODO: this phrase list will go stale as model style changes. The rhythm
# variance signal is the durable one - consider weighting it higher.
def rhythm_variance(text: str):
    sentences = [s for s in _SENTENCE_SPLIT.split(text or "") if _WORD_RE.search(s)]
    lengths = [len(_WORD_RE.findall(s)) for s in sentences]
    if len(lengths) < 4:
        return 0.5
    mean = statistics.mean(lengths)
    if mean <= 0:
        return 0.0
    return round(statistics.pstdev(lengths) / mean, 4)


_NAME = re.compile(r"\b[A-Z][a-z]{2,14}\b")
_EPITHET = re.compile(r"\bthe (\w+ ){1,2}(dragon|cat|dog|girl|boy|rabbit|bear|fox|"
                      r"penguin|owl|mouse|child|robot|witch|lamp)\b", re.I)


def repetition_tells(text: str):
    """Over-naming and repeated openers.

    Caught this from listening to a narration, not from reading one: "the shy
    dragon ... the shy dragon ... the shy dragon" is nearly invisible on the
    page and unbearable out loud. A person writing would have switched to "he"
    after the first mention.
    """
    tells: List[str] = []
    words = _WORD_RE.findall(text or "")
    if len(words) < 40:
        return tells

    # Over-named characters. Threshold is per-100-words so length doesn't skew it.
    counts = Counter(_NAME.findall(text or ""))
    per_hundred = len(words) / 100.0
    for name, n in counts.most_common(4):
        rate = n / per_hundred
        if rate > 2.5 and n >= 4:
            tells.append(
                f'"{name}" appears {n} times ({rate:.1f} per 100 words) - '
                "use he/she/they after the first mention in each paragraph")

    # Repeated epithets ("the shy dragon" twice is once too many).
    epithets = Counter(m.group(0).lower() for m in _EPITHET.finditer(text or ""))
    for phrase, n in epithets.items():
        if n >= 2:
            tells.append(f'the epithet "{phrase}" is used {n} times - use it once at most')

    # Paragraph openers.
    paras = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]
    openers = [re.sub(r"[^a-z]", "", p.split()[0].lower()) for p in paras if p.split()]
    repeats = [w for w, n in Counter(openers).items() if n >= 3 and len(w) > 1]
    if repeats:
        tells.append(
            f"{len(repeats)} word(s) open three or more paragraphs "
            f"({', '.join(repeats[:3])}) - vary how paragraphs start")
    return tells


def structural_tells(text: str):
    tells: List[str] = []
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text or "") if p.strip()]

    if paragraphs:
        last = paragraphs[-1].lower()
        if sum(1 for m in _MORAL_MARKERS if m in last) >= 1 and len(last.split()) > 12:
            tells.append("final paragraph states the moral out loud instead of leaving it in the story")

    tags = _ADVERB_TAG.findall(text or "")
    if len(tags) >= 2:
        tells.append(f"{len(tags)} adverb-laden dialogue tags (\"said excitedly\") - use plain 'said'")

    tricolons = _TRICOLON.findall(text or "")
    if len(tricolons) >= 3:
        tells.append(f"{len(tricolons)} three-item lists - the rhythm becomes mechanical")

    if len(_EM_DASH.findall(text or "")) >= 3:
        tells.append("heavy em-dash use - rare in early-reader prose")

    if len(paragraphs) >= 4:
        lengths = [len(p.split()) for p in paragraphs]
        mean = statistics.mean(lengths)
        if mean > 0 and statistics.pstdev(lengths) / mean < 0.22:
            tells.append("every paragraph is nearly the same length - vary them")

    variance = rhythm_variance(text)
    if variance < 0.38:
        tells.append(
            f"sentence lengths are too uniform (variation {variance:.2f}, aim above 0.45) - "
            "mix very short sentences with longer flowing ones"
        )
    return tells


def humanity_report(text: str):
    """Combined score. 100 = reads as human-written, 0 = generated boilerplate."""
    words = _WORD_RE.findall(text or "")
    n_words = max(1, len(words))

    stock = find_stock_phrases(text)
    structural = structural_tells(text) + repetition_tells(text)

    stock_weight = sum(w for _, w in stock)
    density = round(stock_weight / (n_words / 100.0), 4)

    # Each unit of weighted stock-phrase density costs ~9 points; each
    # structural tell costs 6. Empirically this puts hand-written picture-book
    # text above 85 and untuned gpt-3.5 output in the 45-70 range.
    penalty = min(100.0, density * 9.0 * 3.0 + len(structural) * 6.0)
    score = round(max(0.0, 100.0 - penalty), 2)

    tells = [f'stock phrase: "{p}"' for p, _ in stock[:6]] + structural[:4]
    return {
        "score": score,
        "density": density,
        "tells": tells,
        "stock_phrases": [p for p, _ in stock],
        "rhythm_variance": rhythm_variance(text),
    }
