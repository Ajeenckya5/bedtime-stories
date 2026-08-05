"""Requested reading length: parsing, scaling, and sectioned generation.

The bug these cover: "a 5 minute story" used to produce the same ~600 words as
every other request, because nothing in the pipeline read the words "5 minute".
"""

import pytest

from bedtime.agents.storyteller import _split_beats, _tail
from bedtime.config import QualityGate, Settings
from bedtime.length import (DEFAULT_MINUTES, MAX_MINUTES, MIN_MINUTES,
                            READ_ALOUD_WPM, length_note, minutes_for,
                            parse_minutes, spec_for, words_for)
from bedtime.llm.mock_provider import MockProvider
from bedtime.orchestrator import StoryOrchestrator
from bedtime.schemas import StoryBrief


@pytest.fixture
def settings(tmp_path):
    return Settings(provider="mock", use_moderation_api=False, use_embeddings=False,
                    memory_enabled=False, enable_cache=False,
                    trace_dir=tmp_path / "t", memory_db=tmp_path / "m.sqlite3",
                    cache_db=tmp_path / "c.sqlite3",
                    gate=QualityGate(judge_samples=1, max_revisions=1))


# --- parsing ---------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("a 5 minute story about a dragon", 5.0),
    ("a 5-minute story", 5.0),
    ("a five minute story", 5.0),
    ("tell me a 20 min story", 20.0),
    ("something about 12 minutes long", 12.0),
    ("a 10-15 minute story", 12.5),          # midpoint
    ("a 2 minute one please", 2.0),
])
def test_explicit_minutes_are_parsed(text, expected):
    assert parse_minutes(text) == expected


@pytest.mark.parametrize("text,expected", [
    ("a really long story about space", 15.0),
    ("a long story please", 10.0),
    ("a quick story", 3.0),
    ("just a short one", 3.0),
    ("a really short story", 2.0),
])
def test_vague_length_words_are_mapped(text, expected):
    assert parse_minutes(text) == expected


def test_no_length_mentioned_returns_none():
    assert parse_minutes("a story about a cat who lost a sock") is None
    assert parse_minutes("") is None


def test_minutes_are_clamped_to_the_supported_band():
    assert parse_minutes("a 45 minute epic") == MAX_MINUTES
    assert parse_minutes("a 1 minute story") == MIN_MINUTES


def test_a_number_that_is_not_a_duration_is_ignored():
    """"3 little pigs" is not a request for a three minute story."""
    assert parse_minutes("a story about 3 little pigs") is None
    assert parse_minutes("a story about 101 dogs") is None


# --- the spec --------------------------------------------------------------

def test_words_track_read_aloud_speed_not_silent_reading():
    # 130 wpm, because you do voices and stop when they ask what a heron is
    assert READ_ALOUD_WPM == 130
    assert words_for(5) == 650
    assert minutes_for(650) == 5.0


@pytest.mark.parametrize("minutes,lo,hi", [
    (2, 200, 320), (5, 500, 800), (10, 1000, 1600), (20, 2000, 3100),
])
def test_target_words_scale_with_the_ask(minutes, lo, hi):
    spec = spec_for(minutes)
    assert lo <= spec.target_words <= hi
    assert spec.min_words < spec.target_words < spec.max_words


def test_beats_grow_with_length_but_not_without_limit():
    """A 2-minute story still needs a shape; a 20-minute one does not need
    thirty beats, or the plan stops being a spine and becomes a synopsis."""
    assert spec_for(2).beats >= 3
    assert spec_for(2).beats < spec_for(10).beats < spec_for(20).beats
    assert spec_for(MAX_MINUTES).beats <= 12


def test_only_long_stories_are_written_in_sections():
    assert spec_for(2).sections == 1
    assert spec_for(5).sections == 1
    assert spec_for(20).sections >= 3


def test_default_applies_when_nothing_was_asked_for():
    assert spec_for(None).minutes == DEFAULT_MINUTES


# --- the reviser instruction ----------------------------------------------

def test_length_note_is_silent_when_the_length_is_right():
    spec = spec_for(5)
    assert length_note(spec, spec.target_words) is None


def test_length_note_names_the_gap_in_words_and_minutes():
    """"Make it longer" gets padding. A number gets scenes."""
    note = length_note(spec_for(10), 400)
    assert note and "400 words" in note and "10 min" in note
    assert "900 words short" in note
    assert "do not pad" in note.lower()


def test_length_note_protects_the_ending_when_cutting():
    note = length_note(spec_for(2), 900)
    assert note and "wind-down must stay" in note


# --- section splitting -----------------------------------------------------

def test_beats_split_into_contiguous_non_empty_runs():
    for n_beats in range(3, 13):
        for sections in range(1, 5):
            groups = _split_beats(n_beats, sections)
            assert all(end > start for start, end in groups), "empty section"
            assert groups[0][0] == 0 and groups[-1][1] == n_beats
            for (_, prev_end), (nxt_start, _) in zip(groups, groups[1:]):
                assert prev_end == nxt_start, "gap or overlap between sections"


def test_more_sections_than_beats_is_capped():
    assert len(_split_beats(3, 9)) == 3


def test_tail_is_the_end_not_the_beginning():
    text = " ".join(str(i) for i in range(200))
    assert _tail(text, 5) == "195 196 197 198 199"


# --- end to end ------------------------------------------------------------

@pytest.mark.parametrize("request_text,minutes,sections", [
    ("a 2 minute story about a shy dragon", 2.0, 1),
    ("a 5 minute story about a shy dragon", 5.0, 1),
    ("a 20 minute story about a shy dragon", 20.0, 4),
])
def test_requested_length_reaches_the_brief(request_text, minutes, sections, settings):
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    result = o.tell(request_text)
    assert result.brief.target_minutes == minutes
    assert result.brief.length.sections == sections


def test_asking_for_longer_actually_plans_a_bigger_story(settings):
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    short = o.tell("a 2 minute story about a shy dragon")
    long = o.tell("a 20 minute story about a shy dragon")
    assert long.brief.length.target_words > short.brief.length.target_words * 5
    assert long.brief.length.beats > short.brief.length.beats


def test_brief_without_a_length_still_works():
    brief = StoryBrief(raw_request="a story about a cat", sanitized_request="a story about a cat")
    assert brief.target_minutes is None
    assert brief.length.minutes == DEFAULT_MINUTES


def test_typed_length_beats_the_ui_slider(settings):
    """Someone who typed "a 20 minute story" has already answered the question.

    A slider left at 2 from a previous story must not quietly overrule them.
    """
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    result = o.tell("a 20 minute story about a shy dragon", minutes=2)
    assert result.brief.target_minutes == 20.0


def test_slider_applies_when_the_request_says_nothing(settings):
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    result = o.tell("a story about a shy dragon", minutes=12)
    assert result.brief.target_minutes == 12.0


@pytest.mark.parametrize("minutes", [2, 5, 10, 20])
def test_offline_demo_delivers_the_length_it_was_asked_for(minutes, settings):
    """The mock has to be wrong about the prose, not about the shape.

    It used to return the same ~270-word template whatever you asked for, so
    anyone running the offline demo would ask for twenty minutes, get two, and
    reasonably conclude the feature did not work.
    """
    from bedtime.schemas import RunStatus
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    result = o.tell("a story about a shy dragon", minutes=minutes)
    assert result.status is RunStatus.OK, result.warnings
    words = len(result.story.split())
    spec = result.brief.length
    assert spec.min_words <= words <= spec.max_words * 1.1, (
        f"asked {minutes} min ({spec.target_words}w), got {words}w")
