# Bedtime Story Engine

> **The original assignment brief is preserved verbatim at
> [ASSIGNMENT.md](ASSIGNMENT.md)** — it was moved there unchanged so this file
> could hold the submission write-up. The original skeleton is at
> [`docs/original_skeleton.py`](docs/original_skeleton.py).

A production-shaped bedtime story generator for ages 5–10, built on the provided
skeleton. Takes a plain-English request, plans a story arc, writes it, has an LLM
judge grade it against an anchored rubric, revises against specific feedback, and
refuses to ship anything that fails a safety or readability gate.

Every model call is **`gpt-3.5-turbo`** — locked as a module constant in
`bedtime/config.py` so no config path can override it, per the brief.

> **Note on the model's lifecycle.** OpenAI has scheduled `gpt-3.5-turbo` for
> shutdown on **23 October 2026**. It works today, so the constraint is honoured
> as written. But this is a real production concern, and swapping the model is
> *not* a one-line change: the accept threshold of 82 was derived from this
> model's score distribution, the 75/25 rubric-to-deterministic blend exists
> partly to compensate for gpt-3.5 being miscalibrated, and a good chunk of
> `prompts.py` is scaffolding this model specifically needs. `MIGRATION` in
> `config.py` spells out the three steps in order. The deterministic half of the
> gate is the part that survives a model change unchanged — which is most of the
> argument for having it.

```bash
pip install -r requirements.txt
cp .env.example .env          # add your OPENAI_API_KEY
python main.py                # interactive
```

No key? Everything still runs:

```bash
python main.py --mock "a story about a shy dragon"
```

---

## The system

![block diagram](docs/block_diagram.svg)

Full-size: [`docs/block_diagram.svg`](docs/block_diagram.svg) ·
Mermaid source: [`docs/block_diagram.mmd`](docs/block_diagram.mmd)

```
request → input guardrail → classify → plan → draft
                                                ↓
                        ┌──── revise ←── judge + deterministic validators
                        │                       │
                        └───────────────────────┴──→ output guard → story
```

Six stages, five of them able to stop the run:

| Stage | What it does | Model call? |
|---|---|---|
| **Input guardrail** | length, injection, PII, lexicon, distress routing, LLM semantic screen | 1 |
| **Classifier** | free text → typed `StoryBrief`, picks 1 of 8 category strategies | 1 |
| **Planner** | beat sheet: want / obstacle / lesson / 4–12 beats / motifs / calm ending | 1 |
| **Storyteller** | prose from the plan, temp 0.85, anti-AI-tell prompt | 1–4 |
| **Judge** | 7-dimension anchored rubric × 3 samples, median + spread | 3 |
| **Reviser** | targeted edits from the judge's `must_fix` + quoted offending text | 0–3 |

Typical run: 7–10 calls, ~$0.004, ~25s.

### Story length

Ask for a length and you get one — **2 to 20 minutes** of reading aloud.

```
python main.py --minutes 12 "a story about a shy dragon"
python main.py "a 20 minute story about a shy dragon"    # parsed from the text
```

This used to be broken in a quiet way. The target was a fixed 550–900 words for
everything, so *"a five minute story"* returned the same ~600 words as every
other request — about four minutes — and *"a twenty minute story"* returned that
too. The words `five minute` were read by nothing in the pipeline.

Three things had to change, and the third is the interesting one:

- **Length is parsed by regex, not by the classifier.** `bedtime/length.py`
  reads it off the raw request before any model call. A number the family typed
  is the one part of a request with an exact right answer, and it should not
  make a round trip through a model that is bad at arithmetic. It also means the
  UI can show the target immediately and costs nothing when no length is given.
- **The beat sheet scales.** 4 beats at two minutes, 12 at twenty — capped,
  because past a dozen the plan stops being a spine and becomes a synopsis, and
  the storyteller starts transcribing it instead of writing.
- **Long stories are written in sections.** Ask gpt-3.5-turbo for 2,600 words in
  one call and it doesn't refuse — it writes about 900 good ones and then
  compresses the rest into summary. You can watch it happen: sentences lengthen,
  dialogue stops, the last third reads like a blurb. So past ~900 words the
  story is written in parts against the beat sheet, each call seeing the whole
  plan, its own run of beats, and the tail of the previous part so the seam
  doesn't show.

Reading speed is **130 wpm**, not the 200–250 used for silent adult reading —
you do voices, and you stop when they ask what a heron is. One constant in
`bedtime/length.py` feeds the generator, the shelf's "about 5 minutes" label and
the TTS duration estimate, so they can't drift apart.

If a draft misses the target, the length fix goes to the reviser **first**, and
it names the gap: *"this runs 400 words, about 3 minutes; you asked for 10, it
is 900 words short — do not pad, find the beats being rushed and give them
room."* "Make it longer" gets you padding; a number gets you scenes.

---

## The three things the assignment asked about

### 1. How the LLM judge improves the story

The naive version — *score it, and if it's bad, generate a new one* — throws away
everything good about the draft and oscillates inside the judge's own noise. This
does four things differently:

**Self-consistency.** Three independent judge samples per evaluation, median per
dimension (robust to one wild outlier in a way the mean isn't). The spread
between samples becomes an `agreement` score that ships with the result. Low
agreement means the story sits on a boundary, and that's surfaced rather than
hidden.

**The judge is given measured facts.** Word count, Flesch-Kincaid grade, sentence
lengths and detected AI-tells are computed deterministically and handed to the
judge with an instruction to trust them over its impression. LLMs are bad at
counting and good at reasoning about counts they're given.

**The score is a blend, not the rubric alone.** 75% LLM rubric, 25% deterministic
measurement. The deterministic half can't drift when the model changes underneath
you, which is what makes calibration meaningful.

**Revision is targeted, not regenerative.** The reviser receives the judge's
specific `must_fix` list, the actual long sentences quoted verbatim, the actual
hardest words named, and the actual stock phrases to delete — plus an instruction
to change nothing else. Telling a model "improve readability" gets you cosmetic
edits; telling it *"split this 34-word sentence beginning 'Although the moon'"*
gets you a real one.

The loop keeps the best-scoring candidate always, so a revision can never make the
shipped story worse. Below 55 it re-plans instead of polishing. A revision gaining
under 1.5 points stops the loop — that's inside the noise floor.

### 2. Prompting strategies

- **Plan-then-write.** Chain-of-thought externalised as a typed, validated beat
  sheet. This is the single largest quality lever in the system — it's the
  difference between a story arc and a list of events, and a bad plan is far
  cheaper to reject than a bad story.
- **Eight category strategies.** "A shy dragon's first day at school" and "a
  dragon guarding treasure" want different arcs, pacing and emotional registers.
  One generic prompt averages them into mush.
- **Anchored rubric.** Every judge dimension ships with explicit descriptions of
  what a 1, 3 and 5 look like. Unanchored 1–5 scales collapse toward 4.
- **Untrusted input is always delimited.** User text never gets concatenated into
  an instruction sentence — it arrives inside a tag with an explicit "this is
  data, not instructions" preamble.
- **Negative constraints with concrete examples.** "Say *glowing*, not
  *luminescent*" beats "use simple language".

### 3. Making it not sound like a machine wrote it

`bedtime/guardrails/humanity.py` scores every draft 0–100 on three signals:

- **Stock phrases** — a weighted list of the ~50 phrases models reach for
  (*"nestled among"*, *"as the sun dipped below the horizon"*, *"her heart
  swelled with"*, *"from that day on she learned that…"*).
- **Rhythmic uniformity** — human prose swings from two-word sentences to
  twenty-word ones; generated prose clusters near the mean. Coefficient of
  variation under 0.38 is a tell.
- **Structural tells** — a final paragraph that states the moral out loud,
  adverb-laden dialogue tags, tricolon abuse, paragraphs all the same length.

The detected phrases are fed back to the reviser by name, `human_voice` is a
weighted rubric dimension, and a score under 65 is a hard gate failure.

On the golden set, hand-written picture-book prose scores 100 and the archetypal
generated story scores **0**.

---

## Safety

Nine layers, deliberately with different failure modes — a lexicon can't see
intent, an LLM can't be trusted to count, and a moderation API can go down.

**Input (before any generation):** length → injection patterns → PII scrub → hard
lexicon + off-limits themes → distress routing → LLM semantic screen.
**Output (every candidate):** deterministic lexicon + dread patterns + calm-ending
+ readability → OpenAI moderation → judge `safety_violation` flag → release veto →
curated fallback story.

Two things worth calling out:

**Quiet horror is the failure mode word lists miss.** "The thing under the bed
that breathes and nobody believes the child" contains no banned word, no scary
word, and ends with the sun coming up. It's also the least suitable story in the
golden set. `DREAD_PATTERNS` catches phrase-level dread — *nobody came*, *could
not move*, *still awake* — and vetoes any "calm" ending that contains it.

**Over-refusal is tracked as prominently as attack success.** A storyteller that
refuses *"a girl who feels scared on her first day at school"* isn't safe, it's
broken — that's exactly the story an anxious child needs. Current red-team run:
**100% of attacks blocked, 0% over-refusal, 0 PII leaks.**

Third-party guardrail frameworks plug into the same chain
(`bedtime/guardrails/validators.py`) without replacing the built-ins:

```bash
pip install -r requirements-guardrails.txt
BEDTIME_VALIDATORS=guardrails_ai,nemo python main.py
```

They self-disable if not installed, so the default install has zero extra deps.

---

## The website

```bash
pip install -r requirements.txt
streamlit run app.py
```

Deploying it: [DEPLOY.md](DEPLOY.md). Works with no API key — falls back to the
offline mock and the seed library, which is a perfectly good demo link.

**Two screens.** A *shelf* of covers with filter and search, and a *reading
room*. Opening a story asks how you want it — **📖 I'll read** or **🔊 Read to
me** — rather than assuming. Choosing to listen gives you a voice picker (six
voices, warmest first) and you can still follow along with the text, or close
your eyes.

Serif at 20px with 1.9 line-height and a drop cap, which is roughly what a
children's trade paperback uses. Night palette throughout, because a bright white
page at 8pm is the wrong tool.

Stories you generate join the shelf for the session, with their own cover.

There's a password gate (`APP_PASSWORD`) that's off locally and strongly
recommended on a public deploy — otherwise anyone who finds the URL spends your
OpenAI credit.

### Covers

Every story gets an animated SVG cover, so you can tell what's inside before
reading a word.

**The cover is drawn from the story's contents, not just its category.**
`detect_subjects()` scores concrete nouns across seventeen drawable
subjects — cat, dragon, boat, teapot, rabbit, penguin, tree, house, book, map,
robot, radio, star, lamp, shelf, bird, pool — weighting a title match six times
a body match, because a title names what a story is *about* while the body
mentions everything it passes. A story about a shy dragon gets a dragon; a story
about a lost cat gets a cat. The category only sets the palette and the
backdrop, and only supplies the subject when nothing concrete is found.

**They're drawn in code, not generated.** That was deliberate — an image model
costs ~$0.04 per cover, takes ten seconds, adds a third model to a project whose
brief locks the model, and worst of all is non-deterministic: a different picture
every reload. A child looking for *the cat one* needs it to look the same
tomorrow. A hash of the story id seeds the variations (star positions, hill
height, where the cat sits), so two animal stories don't look identical but each
one is stable forever. Renders in about a millisecond, costs nothing.

Animation is CSS keyframes inside the SVG — drifting clouds, twinkling stars, a
bobbing boat, sparks rising off the teapot.

Static preview of all ten: [`reports/covers_preview.html`](reports/covers_preview.html)

## Narration

Any story can be read aloud:

```bash
python main.py --audio "a story about a shy dragon"
python main.py --audio --voice shimmer "..."
```

Or type `play` in interactive mode after a story appears.

Uses OpenAI TTS (`gpt-4o-mini-tts`, "nova" voice, speed 0.92 — the default pace
is brisk for a sleepy child). Falls back to macOS `say` / pyttsx3 with no key, so
the plumbing works offline. Audio is cached by content hash; ~$0.01 per story.

**The interesting part is the pacing.** The first version marked up every
paragraph break with a pause. On the page that looks reasonable; out loud it
stops dead after every sentence, because paragraphs in this prose style are
often a single line. It sounded like a station announcement.

The fix was to do less: keep the text clean, let the blank lines carry the
breath, and put the performance direction in the engine's `instructions` field
where it belongs. Three beats maximum per story — title, one scene shift, the
closing goodnight. A 15-paragraph story now gets 3 pauses instead of 15.

Listening also surfaced a prose bug reading never would have: *"the shy
dragon... the shy dragon... the shy dragon"*. Nearly invisible on the page,
unbearable aloud. `repetition_tells()` in `guardrails/humanity.py` now flags
over-naming (per-100-word rate), repeated epithets, and repeated paragraph
openers — and feeds them to the reviser by name. The storyteller prompt gained a
matching rule: use a pronoun after the first mention, never reuse an epithet.

## Story memory and caching

**Memory.** Released stories are chunked, embedded and stored in SQLite, so
"another one about Bramble" keeps Bramble consistent across sessions. Chunking
is semantic, not byte-window: one dense *card* per story plus overlapping
paragraph *scenes*. Retrieval is hybrid — exact character-name lookup alongside
cosine search — and the injected context is capped at ~450 words and explicitly
framed as *background, do not retell*.

Embeddings use `text-embedding-3-small`. It is a **non-generative encoder**;
story generation and judging remain `gpt-3.5-turbo` only. Set
`BEDTIME_USE_EMBEDDINGS=false` for a pure-stdlib TF-IDF retriever with no second
model at all — the similarity floor auto-adjusts, because the two vector spaces
have different cosine scales.

**Cache.** Three SQLite namespaces, keyed by model *and* `PROMPT_VERSION` so
editing a prompt invalidates the affected entries automatically:

| Namespace | Key | Default |
|---|---|---|
| `llm` | exact prompt, deterministic calls only | on |
| `plan` | normalised brief → beat sheet; prose still generated fresh | on |
| `story` | normalised request → finished story | **off** |

Full-story reuse is off by default because the failure mode is a child hearing
the identical story twice. Plan reuse gives most of the saving with none of that
risk — same shape, different words.

```bash
make seed          # index the 10-story library
curl localhost:8000/memory/search?q=the+dragon+one
curl localhost:8000/cache/stats
```

## The story library

Ten hand-written stories ship in `bedtime/library/`. They set the quality bar,
give memory a warm start, and act as a regression net: `make seed-check` runs
them through the system's own gate, and `tests/test_library_bias.py` asserts all
ten pass. If a change starts rejecting hand-written picture-book prose, that is
a bug in the change.

Balance is deliberate — 4 girl protagonists, 3 boy, 1 sibling pair, 2
animal/neutral; all 8 categories; names from several cultures, never explained;
adults off their defaults (Rosa's mum fits radiators, Jun's dad does bedtime); a
wheelchair and a two-dad family present without comment.

This paid for itself immediately: seeding the library exposed a false positive
in the dread detector that was failing three hand-written stories on phrases
like *"Malik did not move."* Weak dread markers now require corroboration.

## Hate, prejudice and stereotype guardrail

`bedtime/guardrails/bias.py` splits two different problems:

- **Hate** is a *hard veto* at input and output — never a weighted score. It
  matches the grammar of prejudice ("all X are Y", "inferior race", "go back
  to") rather than a slur list, which generalises across groups and keeps slurs
  out of the repo. Moderation and the LLM screen sit behind it.
- **Stereotype** is *reported, not blocked*. Nobody asks for a hateful bedtime
  story, but generated children's fiction drifts to defaults unprompted: the
  princess who waits to be rescued, "boys don't cry", the grandmother who only
  bakes. Those get flagged to the reviser with the exact sentence to change, and
  an agency-balance check notes when every action in a story belongs to one
  gender.

The storyteller prompt carries a matching **EVERYONE BELONGS** section, and
difference is required to be present and *unremarkable* — the story is about the
lost cat, not about the character being different.

---

## Reports

Each is generated by its own runnable script, and each states its own limitations.

| Report | Generated by | Answers |
|---|---|---|
| [`reports/CALIBRATION_REPORT.md`](reports/) | `python -m bedtime.evaluation.calibrate` | Does the judge rank stories like a human? Where should the threshold sit? How noisy is one sample? |
| [`reports/EVALUATION_REPORT.md`](reports/) | `python -m bedtime.evaluation.run_eval` | Pass rate, score distribution, cost, latency, weakest dimension, per-category spread |
| [`reports/SAFETY_REPORT.md`](reports/) | `python -m bedtime.evaluation.red_team` | Attack block rate, over-refusal rate, PII leaks, known gaps |

```bash
make reports          # runs all three
```

The calibration run isn't decoration — it found two real bugs the first time it
ran: a sustained-dread story passing every check, and the FK floor punishing
genuinely good picture-book prose. Both fixes are in the diff.

---

## Monitoring

Three layers, no external services required:

```bash
python -m bedtime.observability.dashboard   # → reports/dashboard.html
uvicorn bedtime.api:app --port 8000         # → /metrics, /dashboard, /health, /ready
```

- **JSONL traces** — one line per run with nested spans. Every decision, score
  and retry is queryable with `jq`.
- **Prometheus metrics** at `/metrics` — standard naming (`_total`, `_seconds`),
  counters and histograms with p50/p95, sliced by stage and prompt version.
- **HTML dashboard** — score trend against threshold, outcome breakdown,
  guardrail events, time and tokens by stage. Self-contained, opens from
  `file://`.

Alerts worth setting are in [`docs/RUNBOOK.md`](docs/RUNBOOK.md).

---

## Layout

```
main.py                       entry point (keeps the skeleton's call_model)
bedtime/
  config.py                   all tunables; MODEL constant lives here
  schemas.py                  typed contracts between stages
  prompts.py                  every prompt, versioned
  orchestrator.py             the state machine
  cli.py  api.py              interfaces
  agents/                     classifier, planner, storyteller, judge, reviser
  guardrails/                 input, output, lexicons, readability, humanity, validators
  llm/                        provider, resilience, mock
  observability/              metrics, tracing, dashboard
  evaluation/                 golden set, calibrate, run_eval, red_team
tests/                        273 tests, run offline in ~12s
docs/                         diagram, architecture, runbook, design notes
```

## Commands

```bash
make test        # 273 tests, no API key needed
make demo        # offline end-to-end
make reports     # calibration + evaluation + safety
make dashboard   # HTML monitoring view
make serve       # FastAPI on :8000
make check       # tests + secret scan + red team (CI gate)
```

## Guides

- **[docs/INTERVIEW.md](docs/INTERVIEW.md)** — every decision, the alternative I
  rejected, and why. Read this before talking to anyone about the project.
- **[docs/WALKTHROUGH.md](docs/WALKTHROUGH.md)** — build it from an empty folder,
  file by file, with the code and a check after every stage.
- **[BUILD_GUIDE.md](BUILD_GUIDE.md)** — build this yourself from scratch, in
  milestones, with hints instead of answers.
- **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)** — component-by-component detail.
- **[docs/RUNBOOK.md](docs/RUNBOOK.md)** — deploy, monitor, alert, debug.
- **[docs/DESIGN_NOTES.md](docs/DESIGN_NOTES.md)** — decisions, trade-offs, what I'd
  do differently.

## Notes

- `.env` is gitignored; no key is committed. `make check` greps for one.
- The OpenAI **moderation** endpoint is a non-generative classifier, not a chat
  model. Story generation and judging use `gpt-3.5-turbo` exclusively. Disable
  moderation with `BEDTIME_USE_MODERATION_API=false` for a pure-gpt-3.5 system.
- The golden set labels are mine, single-rater. That's enough to tune a threshold
  and catch a wildly miscalibrated judge; it is not enough to claim the judge
  agrees with parents. Stated in the calibration report too.
