import io

import pytest
from svgelements import SVG

from bedtime.library.seed_stories import SEED_STORIES
from bedtime.web.covers import (CH, CW, SHAPE_DROP, SHAPES, TITLE_BAR,
                                all_categories, cover_svg, detect_subjects,
                                foreground_baseline)


def bbox(svg):
    """Real bounds, via svgelements.

    I first wrote this by hand with regex. It could not parse arc commands and
    reported false positives on every crescent moon, which sent me chasing bugs
    that were not there. Use a parser that knows what a path is.
    """
    doc = SVG.parse(io.StringIO(svg))
    lo_x = lo_y = 1e9
    hi_x = hi_y = -1e9
    for el in doc.elements():
        try:
            box = el.bbox()
        except (AttributeError, TypeError):
            continue
        if not box:
            continue
        x0, y0, x1, y1 = box
        lo_x, lo_y = min(lo_x, x0), min(lo_y, y0)
        hi_x, hi_y = max(hi_x, x1), max(hi_y, y1)
    if lo_x > hi_x:
        return 0, 0, 0, 0
    return lo_x, lo_y, hi_x, hi_y


ALL_SIZES = [(400, 260, True), (460, 300, False), (300, 190, False),
             (240, 150, False), (700, 460, True)]


@pytest.mark.parametrize("entry", SEED_STORIES, ids=[s["id"] for s in SEED_STORIES])
def test_seed_cover_stays_in_frame(entry):
    """Regression: geometry used to be hardcoded 400x260 while callers passed
    300x190 and 460x300, so 16 of 18 renders spilled outside the canvas."""
    for w, h, show in ALL_SIZES:
        svg = cover_svg(entry["id"], entry["title"], entry["category"], w, h,
                        show, entry["story"])
        x0, y0, x1, y1 = bbox(svg)
        assert x0 >= -2, f"{entry['id']} @{w}x{h}: overflows left ({x0:.0f})"
        assert y0 >= -2, f"{entry['id']} @{w}x{h}: overflows top ({y0:.0f})"
        assert x1 <= CW + 2, f"{entry['id']} @{w}x{h}: overflows right ({x1:.0f})"
        assert y1 <= CH + 2, f"{entry['id']} @{w}x{h}: overflows bottom ({y1:.0f})"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_every_shape_fits_where_it_gets_placed(shape):
    """Each shape, drawn at the real baseline, must sit inside the canvas.

    Note the wrapper: svgelements needs a complete document. Feeding it a bare
    <g> fragment silently returns nothing useful, which had me convinced eight
    shapes were broken when they were fine.
    """
    y = foreground_baseline(show_title=True)
    body = SHAPES[shape](CW // 2, y, "#ffffff", "#cccccc")
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CW} {CH}">'
           f"{body}</svg>")
    x0, y0, x1, y1 = bbox(svg)
    assert x0 >= -2 and x1 <= CW + 2, f"{shape} too wide: {x0:.0f}..{x1:.0f}"
    assert y0 >= -2, f"{shape} pokes out of the top: {y0:.0f}"
    assert y1 <= CH - TITLE_BAR + 16, f"{shape} runs under the title: {y1:.0f}"


@pytest.mark.parametrize("shape", sorted(SHAPES))
def test_shape_is_not_absurdly_large(shape):
    body = SHAPES[shape](CW // 2, foreground_baseline(), "#ffffff", "#cccccc")
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {CW} {CH}">{body}</svg>'
    x0, y0, x1, y1 = bbox(svg)
    assert x1 - x0 <= 150, f"{shape} is {x1-x0:.0f} wide"
    assert y1 - y0 <= 90, f"{shape} is {y1-y0:.0f} tall"


def test_viewbox_is_fixed_regardless_of_requested_size():
    for w, h, _ in ALL_SIZES:
        svg = cover_svg("x", "T", "magic_wonder", w, h, True, "a teapot")
        assert f'viewBox="0 0 {CW} {CH}"' in svg
        assert 'preserveAspectRatio="xMidYMid meet"' in svg


def test_clip_path_guarantees_nothing_escapes():
    svg = cover_svg("x", "T", "magic_wonder", story="a teapot that hums")
    assert "clipPath" in svg and "clip-path=" in svg


def test_baseline_clears_the_title_bar():
    assert foreground_baseline(True) + SHAPE_DROP <= CH - TITLE_BAR + 16
    assert foreground_baseline(False) + SHAPE_DROP <= CH
    # with no caption there is room to sit lower
    assert foreground_baseline(False) >= foreground_baseline(True)


def test_still_deterministic():
    a = cover_svg("lib01", "T", "animal_friendship", story="a cat")
    b = cover_svg("lib01", "T", "animal_friendship", story="a cat")
    c = cover_svg("lib02", "T", "animal_friendship", story="a cat")
    assert a == b
    assert a != c


@pytest.mark.parametrize("cat", all_categories())
def test_every_category_renders(cat):
    svg = cover_svg(f"x_{cat}", "Title", cat, story="")
    assert svg.startswith("<svg") and svg.rstrip().endswith("</svg>")
    assert "animation" in svg


def test_empty_story_falls_back_without_crashing():
    svg = cover_svg("x", "", "magic_wonder", story="")
    assert svg.startswith("<svg")


def test_root_has_pixel_dimensions_not_percent():
    """An SVG in an <img> data URI is a standalone document.

    width="100%" has nothing to be a percentage of, so browsers fall back to
    300x150 and stretch the artwork. Looked exactly like the geometry was
    broken; it wasn't.
    """
    svg = cover_svg("x", "T", "magic_wonder", story="a teapot")
    root = svg[:svg.index(">") + 1]
    assert f'width="{CW}"' in root and f'height="{CH}"' in root
    assert "%" not in root


def test_root_aspect_matches_viewbox():
    svg = cover_svg("x", "T", "magic_wonder", story="a teapot")
    root = svg[:svg.index(">") + 1]
    import re
    w = int(re.search(r'width="(\d+)"', root).group(1))
    h = int(re.search(r'height="(\d+)"', root).group(1))
    assert (w, h) == (CW, CH)
