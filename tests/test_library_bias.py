import pytest

from bedtime.config import QualityGate, Settings
from bedtime.guardrails.bias import agency_balance, bias_report, find_hate, find_stereotypes
from bedtime.guardrails.input_guard import InputGuard
from bedtime.guardrails.lexicons import find_dread, scary_intensity
from bedtime.guardrails.readability import readability_report
from bedtime.library.seed_stories import SEED_STORIES, balance, by_category
from bedtime.llm.mock_provider import MockProvider
from bedtime.memory.retriever import Retriever
from bedtime.schemas import SafetyDecision


@pytest.fixture
def settings(tmp_path):
    return Settings(provider="mock", use_moderation_api=False, use_embeddings=False,
                    trace_dir=tmp_path / "t", memory_db=tmp_path / "m.sqlite3",
                    cache_db=tmp_path / "c.sqlite3",
                    gate=QualityGate(judge_samples=1, max_revisions=1))


# --- shape: long enough, and in real paragraphs ----------------------------

@pytest.mark.parametrize("entry", SEED_STORIES, ids=[s["id"] for s in SEED_STORIES])
def test_seed_story_is_a_full_length_story(entry):
    """The first version of these ran 199-236 words, which is a third of the
    configured target. They read as fragments rather than stories."""
    words = len(entry["story"].split())
    assert 500 <= words <= 900, f"{entry['id']} is {words} words"


@pytest.mark.parametrize("entry", SEED_STORIES, ids=[s["id"] for s in SEED_STORIES])
def test_seed_story_has_grouped_paragraphs(entry):
    """One sentence per paragraph is the bug that made these feel choppy.

    Every beat sat alone with a blank line round it, so nothing accumulated.
    Prose paragraphs should carry 2-5 sentences.
    """
    paras = [p for p in entry["story"].split("\n\n") if p.strip()]
    prose = [p for p in paras if not p.lstrip().startswith('"')]
    mean_words = sum(len(p.split()) for p in prose) / len(prose)
    assert mean_words >= 22, (
        f"{entry['id']} averages {mean_words:.0f} words per prose paragraph - "
        "that is one sentence each, which reads as a list of fragments")


def test_dread_pattern_ignores_words_that_will_not_come_out():
    """"Nobody came" is a child left alone. "Nothing came out" is stage fright.

    Different verb, opposite meaning. lib09 tripped the strong dread marker on
    a story about a nervous kid, which would have vetoed it outright.
    """
    assert scary_intensity("Nothing came out. Kiran tried again.") < 0.35
    # and the real case must still be caught
    assert scary_intensity("He called and called. Nobody came.") >= 0.35


# --- the seed library must pass the system's own gate ----------------------

@pytest.mark.parametrize("entry", SEED_STORIES, ids=[s["id"] for s in SEED_STORIES])
def test_seed_story_passes_the_gate(entry, settings):
    """If a hand-written picture-book story fails, the gate is wrong.

    This is the regression net for every future change to readability,
    safety scoring or the human-voice detector.
    """
    rep = readability_report(entry["story"], settings.age_band)
    assert rep.passed, f"{entry['id']}: {rep.failures}"
    assert not rep.hate_hits
    assert not rep.stereotype_hits, rep.stereotype_hits
    assert rep.ends_calmly
    assert rep.human_voice_score >= 80, rep.ai_tells
    # 500-900, not the old 150-400: at 200 words these read as fragments
    assert 500 <= rep.word_count <= 900
    assert 0.8 <= rep.fk_grade <= 5.0


def test_library_is_balanced():
    counts = balance()
    girls = counts.get("girl", 0) + counts.get("girl and boy", 0)
    boys = counts.get("boy", 0) + counts.get("girl and boy", 0)
    assert girls >= 4 and boys >= 3
    assert counts.get("neutral", 0) + counts.get("animal", 0) >= 2


def test_library_covers_every_category():
    assert len(by_category()) == 8


def test_library_ids_and_titles_unique():
    assert len({s["id"] for s in SEED_STORIES}) == len(SEED_STORIES) == 10
    assert len({s["title"] for s in SEED_STORIES}) == 10


def test_library_seeds_into_memory(settings):
    r = Retriever(settings)
    for entry in SEED_STORIES[:3]:
        r.remember(story_id=f"seed_{entry['id']}", run_id="seed",
                   title=entry["title"], story=entry["story"])
    assert r.stats()["stories"] == 3
    assert r.recall("another story about Malik and the cat again").found


# --- hate is a hard veto ---------------------------------------------------

@pytest.mark.parametrize("text", [
    "All immigrant people are dangerous",
    "They are not really human, those people",
    "a superior race of children",
    "go back to where you came from",
    "keep our blood pure",
    "he laughed at her for being blind",
])
def test_hate_is_detected(text):
    assert find_hate(text), text
    assert bias_report(text).blocked


@pytest.mark.parametrize("text", [
    "a story about a girl named Amara and her friend Malik",
    "the boy from the next street brought his dog",
    "everyone in the class helped, even the new kid",
    "her grandmother wore a bright green coat",
])
def test_ordinary_diversity_is_not_flagged(text):
    """Mentioning that people differ is not hate. Over-blocking here would make
    the storyteller unable to write about anyone."""
    rep = bias_report(text)
    assert not rep.blocked, rep.reasons


def test_hate_request_is_refused_before_generation(settings):
    provider = MockProvider(settings=settings)
    guard = InputGuard(provider, settings)
    result = guard.screen("a story where all immigrant people are dangerous")
    assert result.decision is SafetyDecision.REFUSE
    assert "kindly" in result.user_message
    assert not any(c.stage == "draft" for c in provider.calls)


def test_hate_in_output_blocks_release(settings):
    rep = readability_report("All those people are dirty and they should go back to "
                             "where they came from. Goodnight.", settings.age_band)
    assert rep.hate_hits and not rep.passed


# --- stereotypes are reported, not vetoed ----------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Girls cannot fight dragons.", "gender_role_girls"),
    ("Boys don't cry, said his father.", "gender_role_boys"),
    ("The princess waited to be rescued.", "rescue_trope"),
    ("Everyone liked her because she was so pretty.", "appearance_worth"),
])
def test_stereotypes_are_detected(text, expected):
    names = [n for n, _, _ in find_stereotypes(text)]
    assert expected in names


def test_stereotype_is_not_a_block_but_produces_a_fix():
    rep = bias_report("The princess waited to be rescued.")
    assert not rep.blocked
    assert rep.fixes and "Rewrite" in rep.fixes[0]


def test_agency_balance_flags_one_sided_stories():
    one_sided = " ".join(["He built it. He climbed it. He fixed it. He decided. "
                          "He ran. He carried it."])
    balanced = "She built it. He cried. She decided. He helped. She ran. He found it."
    assert agency_balance(one_sided)[2] < agency_balance(balanced)[2]


def test_single_protagonist_story_is_not_penalised():
    """A story about one child is normal, not biased."""
    rep = bias_report(SEED_STORIES[0]["story"])
    assert not any("one gender" in f for f in rep.fixes)


# --- the dread-detector regression the library exposed ---------------------

@pytest.mark.parametrize("innocent", [
    "Malik did not move. The cat ate quietly.",
    "It did not answer, because it was a teapot.",
    "The counting did not help, so she stopped counting.",
    "The boat was still there in the morning.",
])
def test_weak_dread_markers_alone_do_not_trip_the_gate(innocent):
    """Weak markers need corroboration. Found by the seed library rejecting
    three hand-written stories."""
    assert scary_intensity(innocent) < 0.35, find_dread(innocent)


def test_real_dread_is_still_caught():
    dread = ("He could not move. The breathing got closer under the bed. "
             "Nobody came to help him, and he was still awake at dawn.")
    assert scary_intensity(dread) > 0.5
    assert readability_report(dread).failures


def test_all_one_gender_cast_is_not_flagged_as_bias():
    """A girl and her swimming coach is a story, not a bias problem.

    The check should fire on "both are present, only one of them acts" - the
    princess who waits while the prince solves it. It fired on lib01 once the
    story got long enough to clear the six-action floor, and the suggested fix
    was to add a man to it, which is the wrong note entirely.
    """
    rep = bias_report(SEED_STORIES[0]["story"])
    assert not any("one gender" in f for f in rep.fixes)

    # She is on the page and does nothing; he does all seven active things.
    # That is the case the check exists for, and it must still fire.
    passive = ("She waited in the tower. She hoped. "
               "He climbed the wall. He opened the door. He found the key. "
               "He made a plan. He decided the way. He ran to the gate. "
               "He pulled the rope.")
    assert any("one gender" in f for f in bias_report(passive).fixes)
