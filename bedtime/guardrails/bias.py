"""Hate and stereotype detection.

Hate is a hard veto. Stereotypes ("girls can't...", the princess who waits) are
reported to the reviser instead - they're not hateful, but they're what actually
shows up in generated children's fiction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Groups whose mention near a hostile construction should raise the stakes.
# Listing the categories, not the terms, keeps this maintainable and keeps
# slurs out of the repository.
PROTECTED_TERMS: Dict[str, Tuple[str, ...]] = {
    "race_ethnicity": ("race", "racial", "ethnic", "ethnicity", "black", "white",
                       "asian", "african", "hispanic", "latino", "arab", "jewish",
                       "indian", "chinese", "mexican", "immigrant", "foreigner",
                       "tribe", "caste", "skin colour", "skin color"),
    "religion": ("muslim", "islam", "christian", "hindu", "jew", "jewish", "sikh",
                 "buddhist", "atheist", "religion", "religious", "infidel"),
    "nationality": ("country", "nationality", "national", "border", "citizen"),
    "disability": ("disabled", "disability", "wheelchair", "blind", "deaf",
                   "autistic", "handicap", "crippled", "retarded", "dumb"),
    "gender": ("girl", "girls", "boy", "boys", "woman", "women", "man", "men",
               "female", "male", "she", "he"),
    "sexuality": ("gay", "lesbian", "queer", "straight", "trans", "transgender"),
    "appearance": ("fat", "skinny", "ugly", "short", "tall", "poor", "rich"),
}

# The grammar of contempt. Group-agnostic on purpose.
HATE_PATTERNS: List[Tuple[str, str, float]] = [
    ("group_generalisation",
     r"\ball\s+(?:of\s+)?(?:the\s+)?\w+\s+(?:people|kids|children|folks|are|were)\s+"
     r"(?:are\s+)?(?:bad|evil|stupid|dirty|lazy|dangerous|liars?|thieves|greedy)", 0.9),
    ("inferiority",
     r"\b(?:inferior|superior|lesser|better)\s+(?:race|people|religion|kind|breed|blood)\b", 1.0),
    ("dehumanisation",
     r"\b(?:they(?:'re| are)|those people)\s+(?:not\s+(?:really\s+)?(?:human|people)|animals|vermin|pests)\b", 1.0),
    ("exclusion",
     r"\b(?:go back to (?:your|where)|don't belong here|not welcome here|"
     r"shouldn't be allowed (?:here|in)|kick them out|send them back)\b", 0.9),
    ("hate_statement",
     r"\b(?:hate|despise|can't stand)\s+(?:all\s+)?(?:\w+\s+)?(?:people|kids|children|"
     r"muslims|jews|christians|hindus|blacks|whites|asians|immigrants|foreigners)\b", 1.0),
    ("supremacy",
     r"\b(?:master race|racial purity|ethnic cleansing|pure blood(?:ed)?|"
     r"keep (?:our|the) (?:race|blood) pure)\b", 1.0),
    ("mockery_of_attribute",
     r"\b(?:laughed at|made fun of|teased)\s+(?:him|her|them|\w+)\s+for\s+"
     r"(?:being|having)\s+(?:\w+\s+)?(?:black|white|fat|poor|blind|deaf|disabled|"
     r"different|foreign|jewish|muslim)", 0.8),
    ("religious_contempt",
     r"\b(?:false|fake|stupid|evil)\s+(?:god|religion|faith|prophet)\b", 0.9),
    ("caste_slur_structure",
     r"\b(?:low|high|untouchable)\s+caste\b", 0.9),
]

# Stereotypes: scored and reported, not vetoed.
# TODO: regex only catches the blatant phrasings. A story can be quietly
# stereotyped without ever writing "girls can't". No good fix short of asking
# the judge, which is what the rubric dimension is for.
STEREOTYPE_PATTERNS: List[Tuple[str, str, str]] = [
    ("gender_role_girls",
     r"\bgirls?\s+(?:can't|cannot|don't|do not|shouldn't|should not|aren't|are not)\b",
     "girls being told what they cannot do"),
    ("gender_role_boys",
     r"\bboys?\s+(?:can't|cannot|don't|do not|shouldn't|should not|aren't|are not)\s+"
     r"(?:cry|be scared|be afraid|play with)", "boys being told not to feel"),
    ("rescue_trope",
     r"\b(?:princess|girl|she)\s+(?:waited|needed|had)\s+(?:to be\s+)?(?:rescued|saved|"
     r"waiting to be (?:rescued|saved))", "a girl waiting to be rescued rather than acting"),
    ("passive_female",
     r"\bthe (?:princess|girl|mother)\s+(?:just\s+)?(?:watched|waited|smiled and waited)\b",
     "a female character with no agency in her own scene"),
    ("domestic_default",
     r"\b(?:mother|mum|mom|grandma|granny)\s+(?:was\s+)?(?:in the kitchen|baking|cooking|"
     r"cleaning|doing the washing)\b(?!.{0,80}\b(?:invent|fix|build|climb|drove|led)\b)",
     "an adult woman appearing only in a domestic role"),
    ("provider_default",
     r"\b(?:father|dad|grandpa)\s+(?:was\s+)?(?:at work|working|earning|the boss)\b"
     r"(?!.{0,80}\b(?:cooked|sang|hugged|read|cried)\b)",
     "an adult man appearing only as a provider"),
    ("appearance_worth",
     r"\b(?:because|since)\s+she\s+was\s+(?:so\s+)?(?:pretty|beautiful|lovely)\b",
     "a girl's worth tied to her appearance"),
    ("bossy_label",
     r"\b(?:she|the girl)\s+was\s+(?:too\s+)?(?:bossy|shrill|dramatic)\b",
     "a gendered pejorative applied to a girl"),
]

_COMPILED_HATE = [(n, re.compile(p, re.I), w) for n, p, w in HATE_PATTERNS]
_COMPILED_STEREOTYPE = [(n, re.compile(p, re.I), d) for n, p, d in STEREOTYPE_PATTERNS]

_FEMALE = re.compile(r"\b(she|her|hers|girl|girls|woman|women|mother|mum|mom|sister|"
                     r"grandma|granny|aunt|daughter|princess|queen)\b", re.I)
_MALE = re.compile(r"\b(he|him|his|boy|boys|man|men|father|dad|brother|grandpa|"
                   r"uncle|son|prince|king)\b", re.I)
_AGENCY = re.compile(r"\b(decided|built|climbed|fixed|led|invented|solved|ran|jumped|"
                     r"chose|made|found|saved|helped|tried|carried|opened|pulled)\b", re.I)


@dataclass
class BiasReport:
    hate_hits: List[Tuple[str, str]] = field(default_factory=list)
    hate_score: float = 0.0
    stereotype_hits: List[Tuple[str, str, str]] = field(default_factory=list)
    protected_mentions: List[str] = field(default_factory=list)
    female_agency: int = 0
    male_agency: int = 0
    agency_balance: float = 1.0     # 1.0 = balanced, 0.0 = entirely one-sided
    blocked: bool = False
    reasons: List[str] = field(default_factory=list)
    fixes: List[str] = field(default_factory=list)


def find_hate(text: str):
    out = []
    for name, pattern, weight in _COMPILED_HATE:
        m = pattern.search(text or "")
        if m:
            out.append((name, m.group(0).strip(), weight))
    return out


def find_stereotypes(text: str) -> List[Tuple[str, str, str]]:
    out = []
    for name, pattern, description in _COMPILED_STEREOTYPE:
        m = pattern.search(text or "")
        if m:
            out.append((name, m.group(0).strip(), description))
    return out


def protected_mentions(text: str) -> List[str]:
    low = (text or "").lower()
    hits = []
    for group, terms in PROTECTED_TERMS.items():
        if any(re.search(r"(?<![a-z])" + re.escape(t) + r"(?![a-z])", low) for t in terms):
            hits.append(group)
    return sorted(hits)


def agency_balance(text: str):
    sentences = re.split(r"(?<=[.!?])\s+", text or "")
    female = male = 0
    for s in sentences:
        if not _AGENCY.search(s):
            continue
        if _FEMALE.search(s):
            female += 1
        if _MALE.search(s):
            male += 1
    total = female + male
    balance = 1.0 if total == 0 else 1.0 - abs(female - male) / total
    return female, male, round(balance, 3)


def bias_report(text: str, *, is_request: bool = False):
    """Hate (blocks) and stereotypes (reported) in one pass."""
    rep = BiasReport()
    text = text or ""

    hate = find_hate(text)
    rep.hate_hits = [(n, m) for n, m, _ in hate]
    rep.hate_score = round(min(1.0, sum(w for _, _, w in hate)), 3)
    rep.protected_mentions = protected_mentions(text)

    if hate:
        rep.blocked = True
        rep.reasons = [f"hateful content ({n}): \"{m}\"" for n, m, _ in hate]

    rep.stereotype_hits = find_stereotypes(text)
    for name, match, description in rep.stereotype_hits:
        rep.fixes.append(
            f'Rewrite "{match}" - it presents {description}. '
            "Give the character their own choice and action instead."
        )

    if not is_request:
        rep.female_agency, rep.male_agency, rep.agency_balance = agency_balance(text)
        # Only comment when there is enough material to be meaningful, and never
        # penalise a legitimate single-protagonist story.
        total = rep.female_agency + rep.male_agency
        # The bias worth flagging is "both are here, only one of them does
        # anything" - the princess who waits while the prince acts. A cast that
        # is simply all one gender is not that. A girl and her swimming coach is
        # a normal story, and telling the writer to add a man to it is the wrong
        # note. So require the quieter gender to actually be on the page.
        both_present = bool(_FEMALE.search(text)) and bool(_MALE.search(text))
        if total >= 6 and rep.agency_balance < 0.25 and both_present:
            rep.fixes.append(
                "Almost every action in this story is taken by characters of one gender. "
                "Let at least one character of another gender make a decision that "
                "changes what happens."
            )
    return rep
