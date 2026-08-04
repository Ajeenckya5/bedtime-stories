"""Word lists and regexes for the deterministic checks.

Two gotchas: HARD_BANNED must match on word boundaries (otherwise "grape" and
"Cassandra" trip it), and SOFT_SCARY terms are scored, not banned - a story
with zero tension is a boring story.
"""

from __future__ import annotations

import re
from typing import Dict, List, Set, Tuple

# --- absolute blocks: never acceptable in a story for 5-10 year olds --------
HARD_BANNED: Set[str] = {
    # violence / death
    "kill", "killed", "killing", "murder", "murdered", "stab", "stabbed",
    "shoot", "shot", "gun", "guns", "rifle", "pistol", "bullet", "bomb",
    "explode", "blood", "bloody", "corpse", "dead body", "slaughter",
    "torture", "strangle", "suffocate", "drown", "drowned", "hang", "hanged",
    # self-harm
    "suicide", "self-harm", "cut myself", "cut himself", "cut herself",
    "overdose", "starve myself",
    # substances
    "drug", "drugs", "cocaine", "heroin", "meth", "beer", "vodka", "whiskey",
    "drunk", "cigarette", "cigarettes", "vape", "smoking",
    # adult content
    "sex", "sexy", "sexual", "naked", "nude", "porn", "kiss on the lips",
    "seduce", "orgasm", "breast", "erotic",
    # slurs / hate handled separately by the moderation API; obvious profanity:
    "damn", "hell", "crap", "shit", "fuck", "bitch", "bastard", "idiot",
    "stupid", "shut up",
    # abuse / grooming red flags
    "our little secret", "don't tell your parents", "dont tell your parents",
    "come with me alone", "take off your clothes",
}

# graded scariness: allowed in moderation, scored, never zero-tolerance
SOFT_SCARY: Dict[str, float] = {
    "afraid": 0.15, "scared": 0.2, "scary": 0.25, "terrified": 0.5,
    "monster": 0.3, "monsters": 0.3, "beast": 0.25, "witch": 0.2,
    "nightmare": 0.45, "screamed": 0.4, "scream": 0.35, "howl": 0.2,
    "dark": 0.1, "darkness": 0.15, "shadow": 0.12, "shadows": 0.12,
    "growl": 0.2, "growled": 0.2, "chase": 0.2, "chased": 0.2,
    "trapped": 0.35, "lost": 0.12, "alone": 0.15, "cried": 0.15,
    "danger": 0.3, "dangerous": 0.3, "storm": 0.15, "thunder": 0.15,
    "claws": 0.25, "teeth": 0.15, "hunt": 0.25, "attack": 0.5,
    "fight": 0.35, "fought": 0.3, "war": 0.6, "weapon": 0.6,
}

# Tension that is developmentally healthy and should not be penalised.
GENTLE_PERIL_ALLOWLIST: Set[str] = {
    "a little scared", "a bit scared", "felt shy", "wobbly", "butterflies in",
    "nervous", "unsure", "worried for a moment", "took a deep breath",
}

# --- calming-ending signals -------------------------------------------------
CALM_ENDING_SIGNALS: Set[str] = {
    "goodnight", "good night", "asleep", "sleep", "sleepy", "dream", "dreams",
    "dreaming", "warm", "cosy", "cozy", "safe", "snug", "tucked", "yawn",
    "quiet", "peaceful", "gentle", "hugged", "smiled", "home", "blanket",
    "pillow", "star", "stars", "moon", "softly", "rest", "still",
}

CLIFFHANGER_SIGNALS: Set[str] = {
    "to be continued", "what happens next", "suddenly", "but then",
    "little did they know", "never came back", "was still out there",
}

# Sustained dread is the failure mode single-word lexicons miss completely.
# g10 in the golden set ("the thing under the bed") contains no banned word,
# no "scary" word, and ends with the sun coming up - yet it is the single most
# unsuitable story in the set. These are phrase-level patterns for a child who
# is alone, unheard, and not helped. Any hit is heavily weighted.
#
# Weight >= 0.9 = strong: one hit is enough on its own. Anything lower is weak
# and needs corroboration, because weak markers have real innocent uses. The
# seed library caught this the hard way: "Malik did not move" (a boy sitting
# still so a cat will trust him), "it did not answer, because it was a teapot"
# and "the counting did not help" were each single-handedly failing the gate.
# A phrase that appears in gentle prose cannot be a solo veto.
DREAD_PATTERNS: List[Tuple[str, float]] = [
    (r"\b(?:no ?body|no one|nothing) (?:came|helped|answered|heard|believed)\b"
     r"(?!.{0,30}\b(?:because|so that|which was fine)\b)", 1.0),
    (r"\bdid not (?:call for|dare|answer the door)\b", 0.6),
    (r"\b(?:could|would) not (?:move|scream|speak|breathe|look away)\b", 1.0),
    (r"\bunder (?:the|his|her|my) bed\b", 0.7),
    # "still there" alone is far too generic - it fires on "the boat was still
    # there in the morning". Needs a subject that implies a watcher.
    (r"\bstill (?:awake|watching|breathing|out there)\b", 0.8),
    (r"\b(?:breathing|breathed) (?:slow|wet|close|louder)", 1.0),
    (r"\bthe (?:door|room) was too far\b", 0.8),
    (r"\b(?:completely|totally) dark\b", 0.5),
    (r"\bgoing to (?:get|eat|take) (?:you|him|her|them)\b", 1.0),
    (r"\bnever (?:saw|came|returned|woke)\b.{0,20}\bagain\b", 0.9),
    (r"\bwatching (?:him|her|them|you) sleep\b", 1.0),
    (r"\bpulled the (?:blanket|covers) over\b", 0.5),
    (r"\bgot closer\b|\bwas getting (?:closer|louder)\b", 0.7),
]

INJECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("instruction_override", re.compile(
        r"\b(ignore|disregard|forget|override|bypass)\b.{0,30}\b"
        r"(previous|prior|above|earlier|all|any|your)\b.{0,20}"
        r"(instruction|prompt|rule|direction|guideline|constrain)", re.I)),
    ("role_reassignment", re.compile(
        r"\b(you are now|act as|pretend (to be|you are)|from now on you|"
        r"new (persona|role|identity)|roleplay as)\b", re.I)),
    ("system_prompt_exfil", re.compile(
        r"\b(system prompt|initial instructions?|your instructions?|"
        r"reveal .{0,15}(prompt|rules)|print .{0,15}(prompt|instructions))\b", re.I)),
    ("delimiter_injection", re.compile(
        r"(<\/?(system|instruction|request|story|plan)>|```system|\[\s*system\s*\]|"
        r"^\s*(system|assistant)\s*:)", re.I | re.M)),
    ("guardrail_disable", re.compile(
        r"\b(no (filter|restrictions?|limits?|guardrails?)|unfiltered|uncensored|"
        r"dan mode|developer mode|jailbreak|without any (rules|restrictions))\b", re.I)),
    ("age_override", re.compile(
        r"\b(for adults only|adult version|not for (kids|children)|"
        r"mature (audience|version)|r-?rated|nsfw)\b", re.I)),
    ("format_hijack", re.compile(
        r"\b(output (only )?(the )?(json|code|sql)|write (me )?(a )?(python|bash|shell) "
        r"(script|code)|curl .{0,20}http)", re.I)),
]

# PII
# Children's first names are the whole point of a personalised story, so we do
# NOT strip names. We strip contact/identifier data that has no business in a
# story request and should not be sent to a third-party API.
# Names are NOT scrubbed - a personalised story is the whole point. Only
# contact details, which have no business going to a third-party API.
PII_PATTERNS: List[Tuple[str, re.Pattern, str]] = [
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.]{2,}\b"), "[email removed]"),
    ("phone", re.compile(r"(?<!\d)(?:\+?\d{1,3}[\s.-]?)?(?:\(\d{2,4}\)[\s.-]?)?\d{3}[\s.-]?\d{3,4}(?:[\s.-]?\d{2,4})?(?!\d)"), "[phone removed]"),
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[id removed]"),
    ("credit_card", re.compile(r"\b(?:\d{4}[\s-]?){3}\d{3,4}\b"), "[card removed]"),
    ("street_address", re.compile(
        r"\b\d{1,5}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+"
        r"(street|st|avenue|ave|road|rd|lane|ln|drive|dr|boulevard|blvd)\b", re.I), "[address removed]"),
    ("url", re.compile(r"https?://\S+|www\.\S+"), "[link removed]"),
]

# off-limits themes for a bedtime story
OFF_LIMITS_THEMES: Dict[str, List[str]] = {
    "graphic_violence": ["gore", "decapitat", "mutilat", "massacre", "brutal"],
    "adult_relationships": ["affair", "divorce fight", "dating app", "one night"],
    "substances": ["get high", "smoke weed", "bar crawl", "hangover"],
    "real_world_trauma": ["school shoot", "terroris", "kidnap", "abduct", "war crime"],
    "medical_distress": ["cancer diagnos", "died of", "funeral for", "terminal illness"],
    "hate": ["hate all", "inferior race", "deserve to suffer"],
}

_WORD_RE = re.compile(r"[a-z']+")


def find_banned(text: str):
    """Word-boundary matched hard-banned terms (and multi-word phrases)."""
    low = text.lower()
    found: List[str] = []
    for term in HARD_BANNED:
        pattern = r"(?<![a-z])" + re.escape(term) + r"(?![a-z])"
        if re.search(pattern, low):
            found.append(term)
    return sorted(found)


def find_dread(text: str) -> List[Tuple[str, float]]:
    low = text.lower()
    hits = []
    for pattern, weight in DREAD_PATTERNS:
        m = re.search(pattern, low)
        if m:
            hits.append((m.group(0).strip(), weight))
    return hits


def scary_intensity(text: str) -> float:
    """Density-normalised fear score in [0, 1]."""
    low = text.lower()
    for phrase in GENTLE_PERIL_ALLOWLIST:
        low = low.replace(phrase, " ")
    words = _WORD_RE.findall(low)
    if not words:
        return 0.0

    density = sum(SOFT_SCARY.get(w, 0.0) for w in words) / (len(words) / 100.0)
    word_component = min(1.0, density / 6.0)

    # Strong markers stand alone. Weak ones only count once corroborated -
    # otherwise a single ordinary "did not move" vetoes a gentle story.
    dread = find_dread(text)
    strong = [w for _, w in dread if w >= 0.9]
    weak = [w for _, w in dread if w < 0.9]
    dread_total = sum(strong) + (sum(weak) if len(weak) >= 2 or strong else 0.0)
    dread_component = min(1.0, dread_total / 1.6)

    return round(min(1.0, max(word_component, dread_component) + 0.15 * min(word_component, dread_component)), 4)


def detect_injection(text: str) -> List[str]:
    return [name for name, pattern in INJECTION_PATTERNS if pattern.search(text)]


def scrub_pii(text: str):
    found: List[str] = []
    cleaned = text
    for name, pattern, replacement in PII_PATTERNS:
        if pattern.search(cleaned):
            found.append(name)
            cleaned = pattern.sub(replacement, cleaned)
    return cleaned, found


def detect_off_limits(text: str):
    low = text.lower()
    return sorted({theme for theme, needles in OFF_LIMITS_THEMES.items()
                   if any(n in low for n in needles)})


def ends_calmly(text: str, tail_words: int = 60) -> bool:
    """Does the last ~60 words settle? Dread overrides cosy vocabulary."""
    words = text.split()
    tail = " ".join(words[-tail_words:]).lower()
    if any(c in tail for c in CLIFFHANGER_SIGNALS):
        return False
    # Dread in the final stretch overrides any cosy vocabulary near it.
    # "He was still awake when the sun came up" contains "sun" and "still" and
    # is not, by any measure, a calm ending. Strong markers only - a weak one
    # in a closing line is usually innocent ("it did not answer, because it was
    # a teapot").
    if any(w >= 0.9 for _, w in find_dread(tail)):
        return False
    return any(re.search(r"(?<![a-z])" + re.escape(s) + r"(?![a-z])", tail)
               for s in CALM_ENDING_SIGNALS)
