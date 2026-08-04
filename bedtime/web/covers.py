"""Animated SVG covers, drawn from what's actually in the story.

First version picked the scene from the category alone. That was lazy and it
showed: "Nadia and the Map With No X" got a sailing boat because it's filed
under adventure, when the story is a hill and a hand-drawn map with no X on it.
"""

import hashlib
import random
import re

# Everything is drawn in this coordinate space, always. The width/height args
# only set the display box - the viewBox scales it. Before this, the scenes used
# hardcoded 400x260 coords while callers passed 300x190 and 460x300, so most of
# the artwork rendered outside the frame. Caught by the bounds test.
CW, CH = 400, 260
GROUND = CH - 62          # where the hills meet the sky
SAFE_TOP = 96             # keep foreground below the stars
TITLE_BAR = 46

# (sky top, sky bottom, ground, accent, detail) + whether it's a night scene
PALETTES = {
    "animal_friendship": ("#2b1f3d", "#7d4f6d", "#3a2a4a", "#ffd39b", "#ffb0a0", True),
    "adventure_quest":   ("#123b52", "#3d8ca0", "#17384a", "#ffd166", "#8ee3d1", False),
    "magic_wonder":      ("#241a45", "#5b3a8e", "#2e2154", "#c9a7ff", "#ffe9a8", True),
    "everyday_courage":  ("#3a2340", "#b3627a", "#4a2c48", "#ffd6a5", "#ffb4a2", False),
    "bedtime_lullaby":   ("#0b1533", "#26355f", "#16213f", "#fff4c2", "#a9c0ff", True),
    "silly_humor":       ("#2d2440", "#c2705f", "#3d3050", "#ffe066", "#7ee8b0", False),
    "curiosity_learning":("#12203f", "#2f5d8a", "#1b2b4d", "#ffe9a8", "#9ad7ff", True),
    "family_belonging":  ("#1e2a24", "#4a6d55", "#26362d", "#ffcf87", "#ffb3a7", True),
}

CATEGORY_LABEL = {
    "animal_friendship": "Animal friend",
    "adventure_quest": "Adventure",
    "magic_wonder": "Magic",
    "everyday_courage": "Being brave",
    "bedtime_lullaby": "Sleepy",
    "silly_humor": "Silly",
    "curiosity_learning": "Curious",
    "family_belonging": "Family",
}

_ANIM = """<style>
 @keyframes drift {from{transform:translateX(-14px)}to{transform:translateX(14px)}}
 @keyframes bob   {0%,100%{transform:translateY(0)}50%{transform:translateY(-5px)}}
 @keyframes sway  {0%,100%{transform:rotate(-3deg)}50%{transform:rotate(3deg)}}
 @keyframes glow  {0%,100%{opacity:.55}50%{opacity:1}}
 @keyframes rise  {0%{transform:translateY(6px);opacity:.5}100%{transform:translateY(-16px);opacity:0}}
 @keyframes ripple{0%,100%{transform:scaleX(1)}50%{transform:scaleX(1.06)}}
 .drift{animation:drift 11s ease-in-out infinite alternate}
 .bob{animation:bob 3.6s ease-in-out infinite}
 .sway{animation:sway 4.4s ease-in-out infinite;transform-origin:50% 100%}
 .glow{animation:glow 4s ease-in-out infinite}
 .spark{animation:rise 3.4s ease-in infinite}
 .ripple{animation:ripple 5s ease-in-out infinite;transform-origin:50% 50%}
</style>"""
# Subject -> words that mean it's in the story. Title matches count for 6.
# TODO: keyword matching, not semantics. 'the boy rode his bike to the pool'
# picks pool, which is right, but 'she felt like a fish out of water' would
# pick penguin. Hasn't bitten yet on real stories.
SUBJECT_WORDS = {
    "cat":     ("cat", "kitten", "paw", "purr", "whisker", "meow"),
    "dragon":  ("dragon", "smoke ring", "scales", "wings"),
    "moon":    ("moon", "moonlight", "crescent"),
    "lamp":    ("lamp", "lantern", "glow", "gold thread"),
    "teapot":  ("teapot", "kettle", "teacup", "hums", "humming"),
    "pool":    ("pool", "swim", "swimming", "water", "float", "shallow end"),
    "map":     ("map", "treasure", "hill", "compass", "loft"),
    "penguin": ("penguin", "seal", "fish", "restaurant", "flipper"),
    "shelf":   ("bookshelf", "shelf", "screws", "flat box", "wonky"),
    "boat":    ("boat", "sail", "ship", "harbour", "harbor", "row"),
    "house":   ("house", "cottage", "front door", "chimney", "rooftop"),
    "radio":   ("radio", "screwdriver", "wire", "drawer", "fix", "broken"),
    "book":    ("classroom", "read out loud", "teacher", "reading", "book"),
    "tree":    ("tree", "garden", "plant", "tomato", "forest", "branch"),
    "star":    ("star", "stars", "starlight", "constellation"),
    "rabbit":  ("rabbit", "bunny", "burrow", "hop"),
    "bird":    ("bird", "owl", "duck", "feather", "nest", "moth"),
    "robot":   ("robot", "gears", "beep", "metal"),
}

# If nothing scores, fall back to something category-appropriate.
CATEGORY_DEFAULT = {
    "animal_friendship": "cat",
    "adventure_quest": "map",
    "magic_wonder": "teapot",
    "everyday_courage": "book",
    "bedtime_lullaby": "lamp",
    "silly_humor": "penguin",
    "curiosity_learning": "star",
    "family_belonging": "house",
}


# Tallest shape measured 80px, extending ~30 below its own origin. Anything
# added to SHAPES needs to stay under that or the baseline maths is wrong.
SHAPE_DROP = 30


def foreground_baseline(show_title=True):
    """Where the foreground sits, so it clears the caption strip."""
    floor = CH - (TITLE_BAR + 12 if show_title else 16)
    return max(SAFE_TOP + 60, min(GROUND + 4, floor - SHAPE_DROP))


def _rng(seed_text):
    seed = int(hashlib.sha256((seed_text or "x").encode()).hexdigest()[:12], 16)
    return random.Random(seed)


def detect_subjects(story, title="", limit=2):
    """Which concrete things are actually in this story?

    Title hits are worth six body hits - a title is the author telling you what
    the story is about, and it's what a child reads first.
    """
    body = (story or "").lower()
    head = (title or "").lower()
    scores = {}
    for subject, words in SUBJECT_WORDS.items():
        n = 0
        for w in words:
            n += len(re.findall(r"(?<![a-z])" + re.escape(w) + r"(?![a-z])", body))
            if w in head:
                n += 6
        if n:
            scores[subject] = n
    ranked = sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))
    if not ranked:
        return []
    top = ranked[0][1]
    # Second subject only if it's genuinely present, not one stray mention.
    keep = [ranked[0][0]]
    for name, score in ranked[1:limit]:
        if score >= max(3, top * 0.5):
            keep.append(name)
    return keep


# --- the pieces. each returns svg positioned around x. ---------------------

def _cat(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="14" rx="26" ry="13" fill="{detail}"/>'
            f'<circle cx="-4" cy="-6" r="13" fill="{detail}"/>'
            f'<path d="M-14,-14 L-10,-26 L-3,-16 Z" fill="{detail}"/>'
            f'<path d="M2,-16 L9,-26 L12,-13 Z" fill="{detail}"/>'
            f'<circle cx="-8" cy="-7" r="1.8" fill="#221a2e"/>'
            f'<circle cx="1" cy="-7" r="1.8" fill="#221a2e"/>'
            f'<path d="M24,10 q16,-6 12,-22" stroke="{detail}" stroke-width="5" '
            f'fill="none" stroke-linecap="round" class="sway"/></g>')


def _dragon(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="8" rx="30" ry="16" fill="{detail}"/>'
            f'<circle cx="20" cy="-10" r="13" fill="{detail}"/>'
            f'<path d="M-6,-6 L-20,-30 L4,-16 Z" fill="{accent}" class="sway"/>'
            f'<path d="M14,-18 L18,-27 L23,-18 Z" fill="{accent}"/>'
            f'<circle cx="25" cy="-12" r="2" fill="#221a2e"/>'
            f'<path d="M-28,4 q-18,4 -14,-14" stroke="{detail}" stroke-width="6" fill="none"/>'
            f'<circle class="spark" cx="34" cy="-8" r="2.4" fill="{accent}"/>'
            f'<circle class="spark" cx="40" cy="-12" r="1.8" fill="{accent}" '
            f'style="animation-delay:1.2s"/></g>')


def _teapot(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="12" rx="32" ry="21" fill="{accent}"/>'
            f'<path d="M28,4 q22,4 12,20" stroke="{accent}" stroke-width="6" fill="none"/>'
            f'<path d="M-30,2 q-18,-2 -14,10" stroke="{accent}" stroke-width="6" fill="none"/>'
            f'<rect x="-9" y="-13" width="18" height="8" rx="3" fill="{accent}"/>'
            f'<circle class="spark" cx="4" cy="-20" r="2.4" fill="{detail}"/>'
            f'<circle class="spark" cx="-6" cy="-24" r="1.8" fill="{detail}" '
            f'style="animation-delay:1.1s"/>'
            f'<circle class="spark" cx="12" cy="-26" r="2" fill="{detail}" '
            f'style="animation-delay:2.2s"/></g>')


def _lamp(x, y, accent, detail):
    return (f'<g transform="translate({x},{y})">'
            f'<circle class="glow" cx="0" cy="-14" r="34" fill="{accent}" opacity=".22"/>'
            f'<path d="M-18,-14 L18,-14 L11,-34 L-11,-34 Z" fill="{detail}"/>'
            f'<rect x="-2" y="-14" width="4" height="30" fill="{detail}"/>'
            f'<ellipse cx="0" cy="17" rx="15" ry="5" fill="{detail}"/>'
            f'<circle class="glow" cx="0" cy="-19" r="7" fill="{accent}"/></g>')


def _pool(x, y, accent, detail):
    return (f'<g transform="translate({x},{y})">'
            f'<rect class="ripple" x="-62" y="-6" width="124" height="32" rx="10" '
            f'fill="{detail}" opacity=".55"/>'
            f'<path class="ripple" d="M-54,6 q14,-5 28,0 t28,0 t28,0 t28,0" '
            f'stroke="{accent}" stroke-width="2" fill="none" opacity=".7"/>'
            f'<g class="bob"><circle cx="0" cy="-16" r="11" fill="{accent}"/>'
            f'<rect x="-9" y="-6" width="18" height="12" rx="6" fill="{accent}"/></g></g>')


def _map(x, y, accent, detail):
    return (f'<g class="sway" transform="translate({x},{y})">'
            f'<path d="M-40,-22 L40,-28 L42,20 L-38,26 Z" fill="{accent}" opacity=".95"/>'
            f'<path d="M-28,-10 q18,10 12,22 M4,-16 q10,14 22,10" stroke="{detail}" '
            f'stroke-width="2" fill="none" opacity=".8"/>'
            f'<circle cx="18" cy="2" r="3" fill="{detail}"/>'
            f'<path d="M-40,-22 L-38,26" stroke="{detail}" stroke-width="1.5" '
            f'opacity=".5"/></g>')


def _penguin(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="4" rx="20" ry="26" fill="#22283d"/>'
            f'<ellipse cx="0" cy="8" rx="13" ry="19" fill="{accent}"/>'
            f'<circle cx="0" cy="-20" r="14" fill="#22283d"/>'
            f'<circle cx="-5" cy="-22" r="2" fill="#fff"/>'
            f'<circle cx="5" cy="-22" r="2" fill="#fff"/>'
            f'<path d="M-4,-15 L4,-15 L0,-9 Z" fill="{detail}"/>'
            f'<ellipse cx="-19" cy="6" rx="5" ry="14" fill="#22283d" class="sway"/>'
            f'<ellipse cx="19" cy="6" rx="5" ry="14" fill="#22283d" class="sway"/></g>')


def _shelf(x, y, accent, detail):
    books = "".join(
        f'<rect x="{-32 + i*11}" y="{-16 + (i % 3)}" width="8" height="{18 - (i%3)*2}" '
        f'rx="1.5" fill="{accent if i % 2 else detail}"/>' for i in range(6))
    return (f'<g transform="translate({x},{y}) rotate(-3)">'
            f'<rect x="-40" y="-24" width="80" height="4" fill="{detail}"/>'
            f'<rect x="-40" y="2" width="80" height="4" fill="{detail}"/>'
            f'<rect x="-42" y="-24" width="4" height="30" fill="{detail}"/>'
            f'<rect x="38" y="-24" width="4" height="30" fill="{detail}"/>'
            f'{books}</g>')


def _boat(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<path d="M-42,8 L42,8 L31,26 L-31,26 Z" fill="{detail}"/>'
            f'<rect x="-2" y="-42" width="4" height="50" fill="{accent}"/>'
            f'<path d="M2,-40 L34,2 L2,2 Z" fill="{accent}" class="sway"/>'
            f'<path d="M-6,-36 L-30,2 L-6,2 Z" fill="{accent}" opacity=".8"/></g>')


def _house(x, y, accent, detail):
    return (f'<g transform="translate({x},{y})">'
            f'<rect x="-42" y="-22" width="84" height="48" rx="4" fill="{detail}"/>'
            f'<path d="M-52,-22 L0,-54 L52,-22 Z" fill="{accent}" opacity=".92"/>'
            f'<rect class="glow" x="-13" y="-9" width="26" height="22" rx="3" fill="{accent}"/>'
            f'<rect x="-1" y="-9" width="2" height="22" fill="{detail}"/>'
            f'<rect x="-13" y="1" width="26" height="2" fill="{detail}"/></g>')


def _radio(x, y, accent, detail):
    return (f'<g transform="translate({x},{y})">'
            f'<rect x="-38" y="-20" width="76" height="42" rx="6" fill="{detail}"/>'
            f'<circle cx="-16" cy="0" r="12" fill="{accent}" opacity=".85"/>'
            f'<circle cx="16" cy="-6" r="5" fill="{accent}"/>'
            f'<circle cx="16" cy="8" r="5" fill="{accent}"/>'
            f'<rect x="-2" y="-34" width="2.5" height="16" fill="{detail}" class="sway"/>'
            f'<circle class="spark" cx="24" cy="-22" r="2" fill="{accent}"/></g>')


def _book(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<path d="M-38,-16 q38,-10 38,4 q0,-14 38,-4 L38,18 q-38,-10 -38,4 '
            f'q0,-14 -38,-4 Z" fill="{accent}"/>'
            f'<path d="M0,-12 L0,22" stroke="{detail}" stroke-width="2"/></g>')


def _tree(x, y, accent, detail):
    return (f'<g transform="translate({x},{y})">'
            f'<rect x="-4" y="-6" width="8" height="28" fill="{detail}"/>'
            f'<g class="sway"><circle cx="0" cy="-22" r="20" fill="{accent}" opacity=".9"/>'
            f'<circle cx="-14" cy="-12" r="13" fill="{accent}" opacity=".85"/>'
            f'<circle cx="14" cy="-13" r="12" fill="{accent}" opacity=".85"/></g></g>')


def _rabbit(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="10" rx="20" ry="15" fill="{detail}"/>'
            f'<circle cx="-2" cy="-8" r="11" fill="{detail}"/>'
            f'<ellipse cx="-7" cy="-24" rx="4" ry="13" fill="{detail}" class="sway"/>'
            f'<ellipse cx="4" cy="-25" rx="4" ry="12" fill="{detail}" class="sway"/>'
            f'<circle cx="-6" cy="-9" r="1.7" fill="#221a2e"/>'
            f'<circle cx="2" cy="-9" r="1.7" fill="#221a2e"/></g>')


def _bird(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<ellipse cx="0" cy="0" rx="16" ry="18" fill="{detail}"/>'
            f'<circle cx="-5" cy="-6" r="3" fill="#fff"/>'
            f'<circle cx="6" cy="-6" r="3" fill="#fff"/>'
            f'<circle cx="-5" cy="-6" r="1.4" fill="#221a2e"/>'
            f'<circle cx="6" cy="-6" r="1.4" fill="#221a2e"/>'
            f'<path d="M-2,-1 L4,-1 L1,4 Z" fill="{accent}"/>'
            f'<path d="M-16,2 q-12,-8 -4,-14" stroke="{detail}" stroke-width="5" '
            f'fill="none" class="sway"/></g>')


def _robot(x, y, accent, detail):
    return (f'<g class="bob" transform="translate({x},{y})">'
            f'<rect x="-20" y="-8" width="40" height="34" rx="6" fill="{detail}"/>'
            f'<rect x="-15" y="-32" width="30" height="24" rx="6" fill="{detail}"/>'
            f'<circle class="glow" cx="-6" cy="-21" r="3.4" fill="{accent}"/>'
            f'<circle class="glow" cx="6" cy="-21" r="3.4" fill="{accent}"/>'
            f'<rect x="-1" y="-42" width="2" height="10" fill="{detail}"/>'
            f'<circle cx="0" cy="-44" r="3" fill="{accent}" class="glow"/></g>')


def _star_cluster(x, y, accent, detail):
    return (f'<g transform="translate({x},{y})">'
            f'<circle class="glow" cx="0" cy="-10" r="4" fill="{accent}"/>'
            f'<circle class="glow" cx="-22" cy="4" r="2.6" fill="{accent}" '
            f'style="animation-delay:1s"/>'
            f'<circle class="glow" cx="20" cy="-2" r="3" fill="{accent}" '
            f'style="animation-delay:2s"/>'
            f'<g class="bob"><circle cx="0" cy="18" r="10" fill="{detail}"/>'
            f'<rect x="-8" y="26" width="16" height="18" rx="6" fill="{detail}"/></g></g>')


SHAPES = {
    "cat": _cat, "dragon": _dragon, "teapot": _teapot, "lamp": _lamp,
    "pool": _pool, "map": _map, "penguin": _penguin, "shelf": _shelf,
    "boat": _boat, "house": _house, "radio": _radio, "book": _book,
    "tree": _tree, "rabbit": _rabbit, "bird": _bird, "robot": _robot,
    "star": _star_cluster,
}

# Things that read better big and centred vs tucked to the side.
_WIDE = {"pool", "shelf", "house", "radio", "boat", "book", "map"}


def _stars(rng, n, colour):
    out = []
    for _ in range(n):
        x, y = rng.randint(12, CW - 12), rng.randint(12, SAFE_TOP + 40)
        r = rng.choice([0.9, 1.2, 1.5, 1.8])
        out.append(f'<circle class="glow" cx="{x}" cy="{y}" r="{r}" fill="{colour}" '
                   f'style="animation-delay:{rng.uniform(0,4):.1f}s"/>')
    return "".join(out)


def _hills(rng, ground):
    a, b = rng.randint(20, 44), rng.randint(24, 52)
    return (f'<path d="M0,{GROUND} Q{CW*0.22:.0f},{GROUND-a} {CW*0.46:.0f},{GROUND-6} '
            f'T{CW},{GROUND-b//2} L{CW},{CH} L0,{CH} Z" fill="{ground}" opacity=".95"/>')


def _moon_shape(x, y, r, colour, crescent=False):
    if not crescent:
        return f'<circle class="glow" cx="{x}" cy="{y}" r="{r}" fill="{colour}"/>'
    return (f'<path class="glow" d="M{x+r*0.35},{y-r} a{r},{r} 0 1,0 0,{2*r} '
            f'a{r*0.78},{r*0.78} 0 1,1 0,-{2*r} Z" fill="{colour}"/>')


def cover_svg(story_id, title, category, width=400, height=260, show_title=True,
              story=""):
    """Build a cover from the story's own subjects. Deterministic per story_id.

    width/height only set the display box. Geometry is always CW x CH and the
    viewBox scales it, so a 300x190 thumbnail and a 460x300 hero are the same
    picture at different sizes.
    """
    category = category if category in PALETTES else "magic_wonder"
    sky_top, sky_bottom, ground, accent, detail, night = PALETTES[category]
    rng = _rng(story_id or title or category)
    gid = f"sky{abs(hash((story_id, category))) % 99999}"

    subjects = detect_subjects(story, title, limit=2)
    if not subjects:
        subjects = [CATEGORY_DEFAULT.get(category, "star")]

    # The moon belongs in the sky, not the foreground. If it's the top hit,
    # hang it up there and let the next subject take the stage.
    celestial = ""
    if "moon" in subjects:
        subjects = [s for s in subjects if s != "moon"]
        celestial = _moon_shape(rng.choice([80, 300]), rng.randint(54, 74),
                                rng.randint(20, 27), accent,
                                crescent=(category == "bedtime_lullaby"))
    elif night:
        celestial = _moon_shape(rng.choice([72, 322]), rng.randint(52, 70),
                                rng.randint(14, 20), accent, crescent=True)
    # Belt and braces: the fallback must be something we can actually draw.
    subjects = [x for x in subjects if x in SHAPES]
    if not subjects:
        fallback = CATEGORY_DEFAULT.get(category, "star")
        subjects = [fallback if fallback in SHAPES else "star"]

    base_y = foreground_baseline(show_title)

    main = subjects[0]
    if len(subjects) == 1:
        fg = SHAPES[main](CW // 2, base_y, accent, detail)
    else:
        # Two subjects: main left of centre, companion right, both well inside.
        fg = (SHAPES[main](int(CW * 0.36), base_y, accent, detail)
              + SHAPES[subjects[1]](int(CW * 0.74), base_y + 4, detail, accent))

    star_count = 22 if category == "bedtime_lullaby" else (14 if night else 5)
    clouds = (f'<g class="drift" opacity=".2">'
              f'<ellipse cx="{rng.randint(70,140)}" cy="{rng.randint(62,92)}" rx="32" '
              f'ry="11" fill="{detail}"/>'
              f'<ellipse cx="{rng.randint(240,330)}" cy="{rng.randint(56,86)}" rx="24" '
              f'ry="9" fill="{detail}"/></g>')

    title_block = ""
    if show_title and title:
        safe = title.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        shown = safe if len(safe) <= 28 else safe[:26].rsplit(" ", 1)[0] + "\u2026"
        title_block = (
            f'<rect x="0" y="{CH-TITLE_BAR}" width="{CW}" height="{TITLE_BAR}" '
            f'fill="#000" opacity=".45"/>'
            f'<text x="{CW//2}" y="{CH-17}" text-anchor="middle" '
            f'font-family="Georgia, serif" font-size="17" fill="#fff8ec">{shown}</text>')

    # Pixel width/height, not 100%. An SVG in an <img> data URI is a standalone
    # document - there is no viewport for a percentage to be relative to, so the
    # browser falls back to 300x150 and stretches the artwork. That was the
    # "covers look out of the box" bug; the drawing itself was always fine.
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CW} {CH}" '
            f'width="{CW}" height="{CH}" preserveAspectRatio="xMidYMid meet" '
            f'style="display:block" role="img" aria-label="{", ".join(subjects)}">{_ANIM}'
            f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0%" stop-color="{sky_top}"/>'
            f'<stop offset="100%" stop-color="{sky_bottom}"/></linearGradient>'
            f'<clipPath id="c{gid}"><rect width="{CW}" height="{CH}" rx="0"/></clipPath>'
            f'</defs><g clip-path="url(#c{gid})">'
            f'<rect width="{CW}" height="{CH}" fill="url(#{gid})"/>'
            f'{_stars(rng, star_count, accent)}{celestial}{clouds}'
            f'{_hills(rng, ground)}{fg}{title_block}</g></svg>')


def category_label(category):
    return CATEGORY_LABEL.get(category, "Story")


def all_categories():
    return list(PALETTES)
