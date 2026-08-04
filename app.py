"""Streamlit front end.

    streamlit run app.py

Two screens: a shelf of covers, and a reading room. Picking a story from the
shelf opens the reading room, where you choose to read it yourself or have it
read to you.
"""

import base64
import os
import sys
from pathlib import Path

import streamlit as st

sys.path.insert(0, str(Path(__file__).parent))

from bedtime.config import MODEL, get_settings
from bedtime.library.seed_stories import SEED_STORIES
from bedtime.prompts import PROMPT_VERSION
from bedtime.schemas import RunStatus
from bedtime.web import theme
from bedtime.web.covers import (all_categories, category_label, cover_svg,
                                detect_subjects)

st.set_page_config(page_title="Bedtime Stories", page_icon="🌙", layout="wide",
                   initial_sidebar_state="collapsed")
theme.inject(st)

# Streamlit Cloud puts config in st.secrets, everything else reads os.environ.
# Bridge them before get_settings() is ever called.
try:
    for _k, _v in st.secrets.items():
        if isinstance(_v, str):
            os.environ.setdefault(_k, _v)
except Exception:
    pass   # no secrets.toml locally, which is the normal case


def password_gate():
    """Password gate. Only active if APP_PASSWORD is set.

    A public URL with a live API key on it is someone else's shopping trip.
    """
    expected = os.environ.get("APP_PASSWORD", "")
    if not expected or st.session_state.get("unlocked"):
        return True
    st.markdown('<div class="masthead"><h1>Bedtime Stories</h1>'
                '<div class="sub">Please enter the password to come in.</div></div>',
                unsafe_allow_html=True)
    pw = st.text_input("Password", type="password", label_visibility="collapsed")
    if pw:
        if pw == expected:
            st.session_state["unlocked"] = True
            st.rerun()
        st.error("Not quite.")
    return False


if not password_gate():
    st.stop()

VOICES = {
    "nova": "Nova — warm, unhurried (default)",
    "shimmer": "Shimmer — soft and light",
    "fable": "Fable — storybook narrator",
    "alloy": "Alloy — plain and clear",
    "echo": "Echo — low and steady",
    "onyx": "Onyx — deep",
}


def state(key, default=None):
    if key not in st.session_state:
        st.session_state[key] = default
    return st.session_state[key]


@st.cache_resource(show_spinner=False)
def get_orchestrator():
    from bedtime.orchestrator import StoryOrchestrator
    return StoryOrchestrator()


@st.cache_resource(show_spinner=False)
def get_narrator(voice):
    # voice is in the key so switching voice rebuilds the engine
    from bedtime.narration.narrator import Narrator
    s = get_settings()
    os.environ["BEDTIME_TTS_VOICE"] = voice
    return Narrator(get_settings(refresh=True))


@st.cache_data(show_spinner=False)
def cover(story_id, title, category, w=400, h=260, show_title=True, story=""):
    return cover_svg(story_id, title, category, w, h, show_title, story)


def svg_img(svg, cls="cover-wrap"):
    b64 = base64.b64encode(svg.encode()).decode()
    return f'<div class="{cls}"><img src="data:image/svg+xml;base64,{b64}"/></div>'


def reading_minutes(text):
    # ~130 wpm read aloud to a child, which is slower than silent reading
    return max(1, round(len(text.split()) / 130))


def open_story(entry):
    st.session_state["open"] = entry
    st.session_state["mode"] = None


# ---- the reading room -----------------------------------------------------

# TODO: session_state only. Refresh the page and the shelf loses anything you
# generated. Should read from the memory store instead.
def reading_room(entry):
    story, title = entry["story"], entry["title"]
    cat = entry.get("category", "magic_wonder")

    if st.button("← Back to the shelf"):
        st.session_state["open"] = None
        st.rerun()

    left, right = st.columns([1, 1.9], gap="large")

    with left:
        st.markdown(svg_img(cover(entry.get("id", title), title, cat, 460, 300,
                                  False, story), "cover-wrap cover-lg"),
                    unsafe_allow_html=True)
        subs = detect_subjects(story, title)
        chips = "".join(f'<span class="chip">{s}</span>' for s in subs)
        st.markdown(f'<span class="chip">{category_label(cat)}</span>{chips}',
                    unsafe_allow_html=True)
        st.markdown(f'<div class="meta">{len(story.split())} words · about '
                    f'{reading_minutes(story)} minutes</div>', unsafe_allow_html=True)

        st.markdown("**How would you like it?**")
        c1, c2 = st.columns(2)
        if c1.button("📖 I'll read", use_container_width=True,
                     type="primary" if st.session_state.get("mode") == "read" else "secondary"):
            st.session_state["mode"] = "read"
            st.rerun()
        if c2.button("🔊 Read to me", use_container_width=True,
                     type="primary" if st.session_state.get("mode") == "listen" else "secondary"):
            st.session_state["mode"] = "listen"
            st.rerun()

        mode = st.session_state.get("mode")
        if mode == "listen":
            settings = get_settings()
            if not settings.tts_enabled:
                st.info("Narration is switched off (BEDTIME_TTS=false).")
            else:
                voice = st.selectbox("Voice", list(VOICES), key="voice",
                                     format_func=lambda v: VOICES[v])
                with st.spinner("Warming up the storyteller's voice…"):
                    n = get_narrator(voice).narrate(story, title)
                if n.ok:
                    st.audio(str(n.audio_path))
                    st.caption(f"{n.voice} · about {n.duration_estimate_s/60:.0f} min"
                               + (" · already made" if n.cached else ""))
                    st.caption("You can follow along on the right, or close your eyes.")
                else:
                    st.warning(f"Couldn't read it aloud: {n.error}")

    with right:
        st.markdown('<div class="reader">', unsafe_allow_html=True)
        st.markdown(f'<div class="story-title">{title}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="story-sub">{category_label(cat)} · '
                    f'{reading_minutes(story)} min</div>', unsafe_allow_html=True)
        paras = "".join(f"<p>{p.strip()}</p>" for p in story.split("\n\n") if p.strip())
        st.markdown(f'<div class="story-text">{paras}</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

    if entry.get("_result"):
        st.markdown("")
        with st.expander("How this story scored"):
            quality_panel(entry["_result"])


# ---- quality panel --------------------------------------------------------

def quality_panel(result):
    a = result.assessment
    if not a:
        st.info("No assessment for this one.")
        return
    d = a.deterministic
    bar = get_settings().gate.accept_threshold

    c = st.columns(4)
    c[0].metric("Quality", f"{a.composite:.0f}", f"{a.composite - bar:+.0f} vs gate")
    c[1].metric("Judge agreement", f"{a.agreement:.0%}", help=f"{a.n_samples} samples")
    c[2].metric("Reading level", f"FK {d.fk_grade:.1f}", help="target 2.0–4.5")
    c[3].metric("Human voice", f"{d.human_voice_score:.0f}",
                help="lower = reads as machine-written")

    st.markdown("###### Rubric")
    for dim, score in sorted(a.dimension_medians.items(), key=lambda kv: -kv[1]):
        st.progress(min(1.0, (score - 1) / 4),
                    text=f"{dim.replace('_', ' ')} — {score:.1f}/5")

    ok = "✅"
    checks = {
        "Banned words": f"{ok} none" if not d.banned_terms else f"⚠️ {d.banned_terms}",
        "Scariness": f"{ok} {d.scary_intensity:.2f} / 0.35 limit",
        "Ends calmly": f"{ok} yes" if d.ends_calmly else "⚠️ no",
        "Hate / prejudice": f"{ok} none" if not d.hate_hits else f"⚠️ {d.hate_hits}",
        "Stereotypes": f"{ok} none" if not d.stereotype_hits else f"⚠️ {d.stereotype_hits}",
        "Machine-writing tells": f"{ok} none" if not d.ai_tells else f"⚠️ {d.ai_tells[:2]}",
    }
    st.markdown("###### Safety checks")
    for k, v in checks.items():
        st.markdown(f'<div class="meta"><b>{k}</b> — {v}</div>', unsafe_allow_html=True)

    if a.fail_reasons:
        st.warning("Gate notes: " + "; ".join(a.fail_reasons[:3]))
    st.caption(f"{result.usage.calls} model calls · ${result.usage.usd:.4f} · "
               f"{result.latency_s:.1f}s · {result.revisions_used} revision(s)")


# ---- the shelf ------------------------------------------------------------

def shelf():
    st.markdown('<div class="section"><h3>The shelf</h3>'
                '<span class="hint">the cover shows what\'s actually inside</span></div>',
                unsafe_allow_html=True)

    f1, f2 = st.columns([2, 3])
    chosen = f1.selectbox("Filter", ["all"] + all_categories(), label_visibility="collapsed",
                          format_func=lambda c: "Everything" if c == "all"
                          else category_label(c))
    search = f2.text_input("Search", placeholder="Search by title or character…",
                           label_visibility="collapsed")

    stories = [s for s in SEED_STORIES + state("made", [])
               if chosen in ("all", s.get("category"))]
    if search.strip():
        q = search.lower().strip()
        stories = [s for s in stories
                   if q in s["title"].lower() or q in s["story"].lower()]

    if not stories:
        st.info("Nothing matches. Try a different filter, or write a new one.")
        return

    for i in range(0, len(stories), 3):
        for col, e in zip(st.columns(3, gap="medium"), stories[i:i + 3]):
            with col:
                st.markdown(svg_img(cover(e.get("id", e["title"]), e["title"],
                                          e.get("category", "magic_wonder"),
                                          story=e["story"])), unsafe_allow_html=True)
                st.markdown(f'<div class="card-title">{e["title"]}</div>',
                            unsafe_allow_html=True)
                st.markdown(f'<span class="chip">'
                            f'{category_label(e.get("category","magic_wonder"))}</span>'
                            f'<span class="chip chip-quiet">'
                            f'{reading_minutes(e["story"])} min</span>',
                            unsafe_allow_html=True)
                if st.button("Open", key=f"open_{e.get('id', e['title'])}",
                             use_container_width=True):
                    open_story(e)
                    st.rerun()


# ---- the generator --------------------------------------------------------

def generator():
    st.markdown('<div class="section"><h3>Tell me a story</h3>'
                '<span class="hint">it gets planned, written, judged and revised '
                'before you see it</span></div>', unsafe_allow_html=True)

    examples = [
        "A story about a girl named Alice and her best friend Bob, who happens to be a cat.",
        "a shy dragon who is scared of his first day at school",
        "why is the moon sometimes out during the day?",
        "something very silly about a penguin who wants to be a chef",
        "a story about my grandma's garden and the tomatoes she grows",
    ]
    cols = st.columns(len(examples))
    for col, ex in zip(cols, examples):
        if col.button(ex.split()[2][:12] + "…", key=f"ex_{ex[:10]}",
                      use_container_width=True, help=ex):
            st.session_state["req"] = ex

    request = st.text_area("What should it be about?", key="req", height=95,
                           placeholder="a story about a brave little boat that "
                                       "is scared of deep water…")

    a, b = st.columns([1, 4])
    if a.button("Write it", type="primary", use_container_width=True) and request.strip():
        with st.spinner("Planning the arc, writing it, then judging it…"):
            result = get_orchestrator().tell(request.strip())
        st.session_state["last"] = result
        if result.status is not RunStatus.REFUSED:
            entry = {
                "id": result.run_id, "title": result.title, "story": result.story,
                "category": result.brief.category.value if result.brief else "magic_wonder",
                "_result": result,
            }
            st.session_state.setdefault("made", []).insert(0, entry)
            open_story(entry)
            st.rerun()

    result = st.session_state.get("last")
    if result and result.status is RunStatus.REFUSED:
        st.error(result.message or "I can't tell that story.")
        st.caption("The guardrail stopped this before anything was generated.")


# ---- app ------------------------------------------------------------------

settings = get_settings()

with st.sidebar:
    st.markdown("### 🌙 Bedtime Stories")
    st.caption(f"`{MODEL}` · prompts `{PROMPT_VERSION}`")
    st.caption(f"Provider: **{settings.provider}**")
    if settings.provider == "mock":
        st.warning("No API key — offline demo. Stories are canned.")
    st.divider()
    st.caption(f"Gate {settings.gate.accept_threshold:.0f} · "
               f"{settings.gate.judge_samples} judge samples · "
               f"≤{settings.gate.max_revisions} revisions")
    if st.session_state.get("made"):
        st.caption(f"{len(st.session_state['made'])} written this session")
    st.divider()
    st.caption("Covers are drawn from the story text, not generated. "
               "Same story, same picture, every time.")

st.markdown('<div class="masthead"><h1>Bedtime Stories</h1>'
            '<div class="sub">Written, checked and read aloud — for ages 5 to 10.</div>'
            '</div>', unsafe_allow_html=True)

if st.session_state.get("open"):
    reading_room(st.session_state["open"])
else:
    t1, t2, t3 = st.tabs(["📚 The shelf", "✨ New story", "🔍 How it works"])
    with t1:
        shelf()
    with t2:
        generator()
    with t3:
        st.markdown("""
#### What happens when you ask for a story

Your request goes through a **guardrail** first — injection patterns, personal
details, hateful or unsuitable topics — before a single word is generated.

A **classifier** works out what kind of story it is and picks one of eight
approaches. A **planner** writes a beat sheet: what the character wants, what
gets in the way, the five beats. Only then does the **storyteller** write.

Then it gets judged. **Measured checks** (reading level, sentence length,
scariness, hate, stereotypes, machine-writing tells) run alongside an **LLM
judge** scoring seven dimensions, three times over, taking the median. The two
blend 75/25 — the measured half can't drift when the model changes.

If it scores below the bar, a **reviser** gets the specific fixes and the
offending sentences quoted, and changes nothing else. The best version always
wins, so revising can never make it worse.
        """)
        st.divider()
        st.markdown("#### The covers")
        st.markdown("""
Read from the story, not from a label. A detector scans for concrete nouns —
cat, teapot, lamp, map, pool, penguin, shelf, radio — weighting a title match
six times heavier, and draws the top one or two.

The first version picked by category and it showed: *Nadia and the Map With No X*
got a sailing boat, because it's filed under adventure. It's a hill and a
hand-drawn map. Now it gets the map.
        """)
        for i in range(0, len(SEED_STORIES), 5):
            for col, e in zip(st.columns(5), SEED_STORIES[i:i + 5]):
                with col:
                    st.markdown(svg_img(cover(e["id"], "", e["category"], 300, 190,
                                              False, e["story"])),
                                unsafe_allow_html=True)
                    st.markdown(f'<div class="meta">{", ".join(detect_subjects(e["story"], e["title"]))}</div>',
                                unsafe_allow_html=True)

st.markdown('<div class="footer">Every story is checked for reading level, '
            'scariness, hate and stereotypes before it reaches you.</div>',
            unsafe_allow_html=True)
