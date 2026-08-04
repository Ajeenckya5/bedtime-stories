import pytest

from bedtime.config import Settings
from bedtime.guardrails.humanity import humanity_report, repetition_tells
from bedtime.narration.narrator import Narrator
from bedtime.narration.pacing import BEAT, build_script, split_for_tts
from bedtime.narration.voice import Narration, audio_key

STORY = """Fen was a dragon who could not do the one thing dragons do.

No smoke. No sparks. Not even a warm puff.

School started on Tuesday. He did not want Tuesday to come.

A dragon called Bo turned around. "Do that again," she said.

By lunch there were six dragons trying to make lumpy ducks.

That night he slept before his mother finished saying goodnight.

Goodnight, Fen. Goodnight, lumpy ducks."""

@pytest.fixture
def settings(tmp_path):
    return Settings(provider="mock", audio_dir=tmp_path / "audio", tts_engine="system")


class FakeEngine:
    name = "fake"
    voice = "test"

    def __init__(self):
        self.calls = []

    def synthesise(self, script, out_path):
        self.calls.append(script)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(b"ID3fake-audio")
        return Narration(audio_path=out_path, duration_estimate_s=script.est_seconds,
                         voice=self.voice, engine=self.name, bytes_written=13)


# pacing

def test_pacing_does_not_break_flow_after_every_sentence():
    """The first version put a pause at every paragraph break. In this prose
    style paragraphs are often one line, so it stopped dead constantly."""
    script = build_script(STORY, title="Fen and the Smoke Rings")
    beats = script.text.count(BEAT.strip())
    # Expect three at most: title, one scene shift, the goodnight. The bug was
    # one per paragraph, so the real check is that beats scale with the story's
    # shape, not with how many paragraphs it happens to have.
    assert beats <= 3, f"{beats} beats for {script.n_segments} paragraphs is too choppy"
    assert beats < script.n_segments / 2
    assert beats < script.n_segments


def test_paragraph_breaks_are_preserved():
    script = build_script(STORY)
    assert "\n\n" in script.text
    assert script.n_segments == 7


def test_closing_lines_get_a_beat():
    script = build_script(STORY, title="T")
    tail = script.text[-200:]
    assert BEAT.strip() in tail


def test_performance_direction_lives_in_instructions_not_markup():
    script = build_script(STORY)
    assert "unhurried" in script.instructions
    assert "do not pause heavily" in script.instructions.lower()
    # No ellipsis littering.
    assert "…" not in script.text


def test_empty_story_is_safe():
    script = build_script("")
    assert script.text == "" and script.n_segments == 0


def test_duration_estimate_is_plausible():
    script = build_script(STORY)
    assert 15 < script.est_seconds < 120


def test_split_never_cuts_mid_paragraph():
    long_story = "\n\n".join(f"Paragraph number {i} has some words in it." for i in range(300))
    chunks = split_for_tts(long_story, max_chars=500)
    assert len(chunks) > 1
    for c in chunks:
        assert not c.startswith(" ") and c.strip()
    assert "".join(c.replace("\n\n", "") for c in chunks).count("Paragraph") == 300


# narrator

def test_narrate_writes_a_file(settings):
    n = Narrator(settings, engine=FakeEngine())
    result = n.narrate(STORY, "Fen and the Smoke Rings")
    assert result.ok and result.audio_path.exists()
    assert result.bytes_written > 0


def test_second_narration_is_cached(settings):
    engine = FakeEngine()
    n = Narrator(settings, engine=engine)
    n.narrate(STORY, "T")
    second = n.narrate(STORY, "T")
    assert second.cached
    assert len(engine.calls) == 1


def test_force_bypasses_cache(settings):
    engine = FakeEngine()
    n = Narrator(settings, engine=engine)
    n.narrate(STORY, "T")
    n.narrate(STORY, "T", force=True)
    assert len(engine.calls) == 2


def test_different_voice_is_a_different_cache_key():
    a = audio_key("same text", "nova", 0.92)
    b = audio_key("same text", "shimmer", 0.92)
    c = audio_key("same text", "nova", 1.0)
    assert a != b and a != c


def test_empty_story_does_not_call_the_engine(settings):
    engine = FakeEngine()
    result = Narrator(settings, engine=engine).narrate("")
    assert not result.ok and not engine.calls


def test_engine_failure_degrades_quietly(settings):
    class Broken:
        name, voice = "broken", "x"

        def synthesise(self, script, out_path):
            return Narration(error="upstream exploded", engine=self.name)

    result = Narrator(settings, engine=Broken()).narrate(STORY, "T")
    assert not result.ok
    assert "exploded" in result.error


def test_play_returns_false_on_a_failed_narration(settings):
    assert Narrator(settings, engine=FakeEngine()).play(Narration(error="nope")) is False


# repetition (the "shy dragon shy dragon" problem)

def test_over_naming_is_flagged():
    repetitive = """The shy dragon woke up early. The shy dragon did not want to go.

The shy dragon put on his bag. Fen looked at the door. Fen counted to ten.

The shy dragon walked slowly. Fen was scared. Fen kept going. Fen arrived.

Fen sat down at the back and Fen said nothing at all."""
    tells = repetition_tells(repetitive)
    assert any("Fen" in t and "times" in t for t in tells)
    assert any("epithet" in t for t in tells)


def test_repeated_paragraph_openers_are_flagged():
    text = "\n\n".join(
        ["Then he walked on to the next field and looked around at the sheep."] * 5)
    assert any("open three or more" in t for t in repetition_tells(text))


def test_clean_prose_is_not_flagged():
    assert repetition_tells(STORY) == []


def test_repetition_lowers_the_human_voice_score():
    repetitive = """The shy dragon woke early. The shy dragon did not want to go.

The shy dragon put on his bag. Fen looked at the door. Fen counted to ten.

The shy dragon walked. Fen was scared. Fen kept going. Fen arrived at last."""
    assert humanity_report(repetitive)["score"] < humanity_report(STORY)["score"]


def test_short_text_is_not_penalised():
    assert repetition_tells("Fen ran. Fen stopped.") == []
