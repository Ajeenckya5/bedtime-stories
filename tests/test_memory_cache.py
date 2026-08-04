import pytest

from bedtime.config import MODEL, QualityGate, Settings
from bedtime.llm.cache import PersistentCache, normalise
from bedtime.llm.mock_provider import MockProvider
from bedtime.memory.chunker import chunk_story, make_scenes, paragraphs
from bedtime.memory.embeddings import CachedEmbedder, TfidfEmbedder, cosine, pack, unpack
from bedtime.memory.retriever import Retriever
from bedtime.memory.store import MemoryStore
from bedtime.orchestrator import StoryOrchestrator
from bedtime.schemas import RunStatus

STORY = """Fen was a dragon who could not do the one thing dragons do.

No smoke. No sparks. Not even a warm puff.

School started on Tuesday. Fen did not want Tuesday to come.

He sat at the back and kept his mouth shut. When the teacher asked everyone to
breathe fire, Fen breathed a wisp of grey nothing.

A dragon called Bo turned around. "Do that again," she said.

Fen did it again. The grey nothing floated up and made a shape a bit like a rabbit.

By lunch there were six dragons trying to make lumpy ducks, and only Fen could do it.

He walked home tired in a good way, and slept before his mother finished saying goodnight."""

@pytest.fixture
def settings(tmp_path):
    return Settings(
        provider="mock", use_moderation_api=False,
        trace_dir=tmp_path / "traces",
        memory_db=tmp_path / "memory.sqlite3",
        cache_db=tmp_path / "cache.sqlite3",
        use_embeddings=False,           # tfidf: no network in tests
        gate=QualityGate(judge_samples=1, max_revisions=1),
    )


# --- chunking --------------------------------------------------------------

def test_paragraph_boundaries_are_respected():
    for chunk in make_scenes("s1", STORY, target_words=60, overlap_words=15):
        # No chunk may start or end mid-paragraph.
        assert chunk.text.strip() == chunk.text
        for para in paragraphs(chunk.text):
            assert para in STORY


def test_scenes_overlap_so_beats_are_not_split():
    scenes = make_scenes("s1", STORY, target_words=60, overlap_words=25)
    assert len(scenes) >= 2
    overlapping = sum(
        1 for a, b in zip(scenes, scenes[1:])
        if set(paragraphs(a.text)) & set(paragraphs(b.text))
    )
    assert overlapping >= 1


def test_oversized_paragraph_becomes_its_own_chunk():
    big = "word " * 400
    scenes = make_scenes("s1", f"Short one.\n\n{big}", target_words=100)
    assert any(c.metadata.get("oversized") for c in scenes)


def test_card_leads_with_names_and_title():
    chunks = chunk_story("s1", "Fen and the Smoke Rings", STORY)
    card = chunks[0]
    assert card.kind == "card"
    assert "Fen and the Smoke Rings" in card.text
    assert card.ordinal == 0


def test_empty_story_produces_no_scenes():
    assert make_scenes("s1", "") == []


# --- embeddings ------------------------------------------------------------

def test_cosine_bounds():
    assert cosine([1.0, 0.0], [1.0, 0.0]) == pytest.approx(1.0)
    assert cosine([1.0, 0.0], [0.0, 1.0]) == pytest.approx(0.0)
    assert cosine([], [1.0]) == 0.0


def test_pack_unpack_roundtrip():
    vec = [0.5, -0.25, 0.125]
    assert unpack(pack(vec)) == pytest.approx(vec)


def test_tfidf_ranks_related_text_higher():
    e = TfidfEmbedder(dim=256)
    q, related, unrelated = e.embed([
        "a story about a shy dragon called Fen who cannot breathe fire",
        "Fen the dragon made smoke rings at dragon school",
        "a penguin opened a restaurant that served only fish",
    ])
    assert cosine(q, related) > cosine(q, unrelated)


def test_embedding_cache_avoids_recompute(tmp_path):
    class Counting(TfidfEmbedder):
        name = "counting"
        calls = 0

        def embed(self, texts):
            Counting.calls += 1
            return super().embed(texts)

    cached = CachedEmbedder(Counting(dim=64), tmp_path / "emb.sqlite3")
    cached.embed(["hello there"])
    cached.embed(["hello there"])
    assert Counting.calls == 1


# --- store -----------------------------------------------------------------

def test_store_roundtrip_and_search(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    embedder = TfidfEmbedder(dim=256)
    chunks = chunk_story("s1", "Fen and the Smoke Rings", STORY)
    vectors = embedder.embed([c.text for c in chunks])
    store.add_story("s1", "Fen and the Smoke Rings", STORY, chunks, vectors,
                    characters=["Fen", "Bo"], category="everyday_courage")

    assert store.stats()["stories"] == 1
    assert store.get_story("s1")["title"] == "Fen and the Smoke Rings"

    q = embedder.embed(["the dragon who could not breathe fire"])[0]
    hits = store.search(q, top_k=3, min_score=0.0)
    assert hits and hits[0].story_id == "s1"
    assert hits == sorted(hits, key=lambda h: -h.score)


def test_store_find_by_character(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    store.add_story("s1", "Fen and the Smoke Rings", STORY, [], [], characters=["Fen"])
    assert store.find_by_character("Fen")
    assert not store.find_by_character("Zebedee")


def test_store_forget_removes_chunks(tmp_path):
    store = MemoryStore(tmp_path / "m.sqlite3")
    embedder = TfidfEmbedder(dim=64)
    chunks = chunk_story("s1", "T", STORY)
    store.add_story("s1", "T", STORY, chunks, embedder.embed([c.text for c in chunks]))
    assert store.forget("s1")
    assert store.stats() == {**store.stats(), "stories": 0, "chunks": 0}


# --- retriever -------------------------------------------------------------

def test_recall_is_quiet_without_a_continuity_cue(settings):
    r = Retriever(settings)
    r.remember(story_id="s1", run_id="r1", title="Fen and the Smoke Rings", story=STORY)
    # Unrelated request with no "again"/name cue must not inject anything.
    assert not r.recall("a story about a penguin chef").found


def test_recall_fires_on_explicit_continuity(settings):
    r = Retriever(settings)
    r.remember(story_id="s1", run_id="r1", title="Fen and the Smoke Rings", story=STORY)
    found = r.recall("tell me another one about Fen the dragon again")
    assert found.found and found.requested_explicitly
    assert "Fen" in found.block


def test_continuity_block_is_budgeted_and_framed(settings):
    r = Retriever(settings)
    for i in range(4):
        r.remember(story_id=f"s{i}", run_id=f"r{i}", title=f"Fen story {i}", story=STORY)
    block = r.recall("another Fen dragon story again").block
    assert len(block.split()) <= settings.memory_context_words + 60
    assert "do not retell" in block.lower()
    assert "consistent" in block.lower()


def test_index_failure_never_raises(settings, monkeypatch):
    r = Retriever(settings)
    monkeypatch.setattr(r.embedder, "embed", lambda texts: (_ for _ in ()).throw(RuntimeError("boom")))
    assert r.remember(story_id="s1", run_id="r1", title="T", story=STORY) == 0


# --- cache -----------------------------------------------------------------

def test_normalise_collapses_phrasing():
    assert normalise("A story about a cat named Bob!") == normalise("story about a cat named bob")


def test_cache_roundtrip_and_ttl(tmp_path):
    c = PersistentCache(tmp_path / "c.sqlite3", MODEL, "v1", ttl_days=1)
    k = c.key("llm", "sys", "user")
    assert c.get("llm", k) is None
    c.put("llm", k, {"text": "hi"})
    assert c.get("llm", k)["text"] == "hi"
    c.put("llm", k, {"text": "stale"}, ttl_seconds=-1)
    assert c.get("llm", k) is None


def test_cache_survives_restart(tmp_path):
    path = tmp_path / "c.sqlite3"
    c1 = PersistentCache(path, MODEL, "v1")
    c1.put("plan", c1.key("plan", "x"), {"title": "T"})
    c2 = PersistentCache(path, MODEL, "v1")
    assert c2.get("plan", c2.key("plan", "x"))["title"] == "T"


def test_prompt_version_change_invalidates(tmp_path):
    path = tmp_path / "c.sqlite3"
    old = PersistentCache(path, MODEL, "v1")
    old.put("plan", old.key("plan", "x"), {"title": "T"})
    new = PersistentCache(path, MODEL, "v2")
    assert new.invalidate_stale_versions() >= 1
    assert new.get("plan", new.key("plan", "x")) is None


def test_cache_disabled_is_inert(tmp_path):
    c = PersistentCache(tmp_path / "c.sqlite3", MODEL, "v1", enabled=False)
    c.put("llm", "k", {"text": "hi"})
    assert c.get("llm", "k") is None


def test_broken_cache_does_not_raise(tmp_path):
    c = PersistentCache(tmp_path / "c.sqlite3", MODEL, "v1")
    c.db_path.write_bytes(b"this is not a database")
    assert c.get("llm", "k") is None      # degrades, does not explode
    c.put("llm", "k", {"text": "hi"})


# --- end to end ------------------------------------------------------------

def test_second_story_gets_continuity(settings):
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    first = o.tell("a story about a dragon named Bramble who is shy")
    assert first.status is RunStatus.OK
    assert o.retriever.stats()["stories"] == 1

    second = o.tell("another one about Bramble the dragon again")
    assert second.status is RunStatus.OK
    assert any("continuity from" in w for w in second.warnings)


def test_plan_cache_hits_on_repeat(tmp_path):
    # Memory off: a second request naming Bob legitimately triggers continuity,
    # which correctly bypasses the plan cache. Isolate the cache behaviour.
    s = Settings(provider="mock", use_moderation_api=False, memory_enabled=False,
                 trace_dir=tmp_path / "t", cache_db=tmp_path / "c.sqlite3",
                 gate=QualityGate(judge_samples=1, max_revisions=1))
    o = StoryOrchestrator(MockProvider(settings=s), s)
    o.tell("a story about a cat named Bob")
    o.tell("A story about a cat named Bob!")
    assert o.cache.stats()["namespaces"]["plan"]["hits"] >= 1


def test_continuity_bypasses_plan_cache(settings):
    """A follow-up must not reuse the plan of the story it follows."""
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    o.tell("a story about a dragon named Bramble")
    before = o.cache.stats()["namespaces"].get("plan", {}).get("hits", 0)
    o.tell("another one about Bramble the dragon again")
    after = o.cache.stats()["namespaces"].get("plan", {}).get("hits", 0)
    assert after == before


def test_story_cache_off_by_default(settings):
    assert settings.story_cache_enabled is False
    o = StoryOrchestrator(MockProvider(settings=settings), settings)
    a = o.tell("a story about a cat named Bob")
    b = o.tell("a story about a cat named Bob")
    assert "served from story cache" not in b.warnings
    assert a.run_id != b.run_id


def test_story_cache_when_enabled(tmp_path):
    s = Settings(provider="mock", use_moderation_api=False, story_cache_enabled=True,
                 trace_dir=tmp_path / "t", memory_db=tmp_path / "m.sqlite3",
                 cache_db=tmp_path / "c.sqlite3", use_embeddings=False,
                 gate=QualityGate(judge_samples=1, max_revisions=1))
    o = StoryOrchestrator(MockProvider(settings=s), s)
    first = o.tell("a story about a cat named Bob")
    second = o.tell("a story about a cat named Bob")
    assert "served from story cache" in second.warnings
    assert second.story == first.story


def test_memory_disabled_short_circuits(tmp_path):
    s = Settings(provider="mock", use_moderation_api=False, memory_enabled=False,
                 trace_dir=tmp_path / "t", cache_db=tmp_path / "c.sqlite3",
                 gate=QualityGate(judge_samples=1, max_revisions=1))
    o = StoryOrchestrator(MockProvider(settings=s), s)
    assert o.retriever is None
    assert o.tell("a story about a fox").status is RunStatus.OK
