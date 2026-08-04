"""Flesch-Kincaid, sentence stats and the deterministic gate. Pure stdlib."""

import re
from typing import List, Optional

from ..config import AgeBand
from ..schemas import DeterministicReport
from .bias import bias_report
from .humanity import humanity_report
from .lexicons import ends_calmly, find_banned, find_dread, scary_intensity

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])[\"')\]]*\s+|\n{2,}")
_WORD_RE = re.compile(r"[A-Za-z][A-Za-z'-]*")
_VOWEL_GROUPS = re.compile(r"[aeiouy]+")
_DIALOGUE_RE = re.compile(r'"[^"]{2,}"')


def split_sentences(text: str):
    parts = [s.strip() for s in _SENTENCE_SPLIT.split(text or "") if s and s.strip()]
    return [p for p in parts if _WORD_RE.search(p)]


def words_in(text: str) -> List[str]:
    return _WORD_RE.findall(text or "")


def count_syllables(word: str):
    """Vowel-group heuristic. Good to about +/-1 on children's vocabulary."""
    w = word.lower().strip("'-")
    if not w:
        return 0
    if len(w) <= 3:
        return 1
    w = re.sub(r"(?:[^laeiouy]es|[^laeiouy]e)$", "", w)
    w = re.sub(r"^y", "", w)
    groups = _VOWEL_GROUPS.findall(w)
    n = len(groups)
    # Common two-syllable endings the heuristic collapses.
    if re.search(r"(ia|io|ua|uo|eo)", w):
        n += 1
    if w.endswith(("le", "les")) and len(w) > 2 and w[-3] not in "aeiouy":
        n += 1
    if w.endswith("ed") and not re.search(r"[td]ed$", w):
        n -= 1
    return max(1, n)


def flesch_kincaid_grade(text: str) -> float:
    """0.39*(words/sent) + 11.8*(syll/word) - 15.59"""
    sentences = split_sentences(text)
    words = words_in(text)
    if not sentences or not words:
        return 0.0
    syllables = sum(count_syllables(w) for w in words)
    return round(
        0.39 * (len(words) / len(sentences)) + 11.8 * (syllables / len(words)) - 15.59, 3
    )


def _band_penalty(value: float, low: float, high: float, target: float, weight: float):
    if low <= value <= high:
        # Small taper toward target so 'comfortably central' beats 'just inside'.
        span = max(high - target, target - low) or 1.0
        return weight * 0.25 * (abs(value - target) / span)
    distance = (low - value) if value < low else (value - high)
    span = max(high - low, 1e-6)
    return weight * min(1.0, 0.25 + distance / span)


def readability_report(text: str, band: Optional[AgeBand] = None):
    band = band or AgeBand()
    text = text or ""
    sentences = split_sentences(text)
    words = words_in(text)
    rep = DeterministicReport()

    if not words:
        rep.passed = False
        rep.failures = ["empty story"]
        rep.readability_score = 0.0
        return rep

    sentence_word_counts = [len(words_in(s)) for s in sentences] or [len(words)]
    rep.word_count = len(words)
    rep.sentence_count = len(sentences)
    rep.mean_sentence_words = round(sum(sentence_word_counts) / len(sentence_word_counts), 2)
    rep.max_sentence_words = max(sentence_word_counts)
    rep.fk_grade = flesch_kincaid_grade(text)
    complex_words = [w for w in words if count_syllables(w) >= 3]
    rep.complex_word_ratio = round(len(complex_words) / len(words), 4)
    rep.dialogue_ratio = round(
        sum(len(words_in(m)) for m in _DIALOGUE_RE.findall(text)) / len(words), 4
    )
    rep.banned_terms = find_banned(text)
    rep.scary_intensity = scary_intensity(text)
    rep.ends_calmly = ends_calmly(text)

    bias = bias_report(text)
    rep.hate_hits = [f"{name}: {match}" for name, match in bias.hate_hits]
    rep.stereotype_hits = [f"{d} (\"{m}\")" for _, m, d in bias.stereotype_hits]
    rep.bias_fixes = bias.fixes
    rep.agency_balance = bias.agency_balance

    human = humanity_report(text)
    rep.human_voice_score = float(human["score"])
    rep.ai_tell_density = float(human["density"])
    rep.ai_tells = list(human["tells"])

    # --- 0-100 readability score ------------------------------------------
    penalty = 0.0
    penalty += _band_penalty(rep.fk_grade, band.fk_grade_floor, band.fk_grade_ceiling,
                             band.target_fk_grade, weight=0.40)
    penalty += _band_penalty(rep.mean_sentence_words, band.sentence_words_floor,
                             band.sentence_words_ceiling, band.target_sentence_words, weight=0.30)
    if rep.complex_word_ratio > band.max_complex_word_ratio:
        over = rep.complex_word_ratio - band.max_complex_word_ratio
        penalty += 0.20 * min(1.0, over / band.max_complex_word_ratio)
    if rep.max_sentence_words > band.max_sentence_words_hard:
        over = rep.max_sentence_words - band.max_sentence_words_hard
        penalty += 0.10 * min(1.0, over / band.max_sentence_words_hard)
    rep.readability_score = round(max(0.0, 100.0 * (1.0 - penalty)), 2)

    # --- hard failures -----------------------------------------------------
    failures: List[str] = []
    if rep.banned_terms:
        failures.append(f"banned terms present: {', '.join(rep.banned_terms[:5])}")
    if rep.hate_hits:
        # Hard fail, no scoring, no partial credit.
        failures.append(f"hateful or prejudiced content: {rep.hate_hits[0]}")
    if rep.scary_intensity > 0.35:
        dread = find_dread(text)
        detail = f" (dread markers: {', '.join(d for d, _ in dread[:3])})" if dread else ""
        failures.append(
            f"scary intensity {rep.scary_intensity:.2f} exceeds 0.35 for ages 5-10{detail}")
    if not rep.ends_calmly:
        failures.append("ending is not calm/settled (bedtime stories must wind down)")
    if rep.fk_grade > band.fk_grade_ceiling:
        failures.append(f"reading level too high (FK {rep.fk_grade} > {band.fk_grade_ceiling})")
    if rep.mean_sentence_words > band.sentence_words_ceiling:
        failures.append(
            f"sentences too long (mean {rep.mean_sentence_words} > {band.sentence_words_ceiling} words)")
    if rep.max_sentence_words > band.max_sentence_words_hard + 8:
        failures.append(f"a sentence runs {rep.max_sentence_words} words")
    if rep.complex_word_ratio > band.max_complex_word_ratio * 1.6:
        failures.append(f"too many long words ({rep.complex_word_ratio:.1%})")

    rep.failures = failures
    rep.passed = not failures
    return rep


def hardest_words(text: str, limit: int = 12):
    seen, scored = set(), []
    for w in words_in(text):
        lw = w.lower()
        if lw in seen or len(lw) < 7:
            continue
        seen.add(lw)
        syl = count_syllables(lw)
        if syl >= 3:
            scored.append((syl, len(lw), w))
    scored.sort(reverse=True)
    return [w for _, _, w in scored[:limit]]


def long_sentences(text: str, threshold: int = 22, limit: int = 5) -> List[str]:
    out = [s for s in split_sentences(text) if len(words_in(s)) > threshold]
    out.sort(key=lambda s: len(words_in(s)), reverse=True)
    return out[:limit]
