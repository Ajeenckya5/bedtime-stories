# Build this yourself

A milestone-by-milestone guide to building the whole system from the bare
skeleton. Hints and checkpoints, not copy-paste answers — you'll understand it
far better if you write it.

Each milestone is independently useful. Stop at 4 and you have something good.
Go to 10 and you have something you could deploy.

**Time estimate:** milestones 1–4 are the core (~90 min). 5–7 are the production
layer (~60 min). 8–10 are polish and proof (~60 min).

---

## Before you start

```bash
python -m venv .venv && source .venv/bin/activate
pip install openai pydantic pytest
```

Put your key in `.env` and add `.env` to `.gitignore` **first**. OpenAI scans
GitHub and auto-revokes leaked keys.

One rule for the whole build: **the model stays `gpt-3.5-turbo`.** Make it a
module-level constant, not a config field. If it can be overridden by an env var,
someone will override it.

---

## Milestone 1 — One good prompt

**Goal:** a single call that reliably produces a decent story.

Start by running the skeleton as-is and reading what comes out. You need to see
the baseline before you can tell whether anything you do helps.

Then write a system prompt. Put these in it:

- Who's listening (a sleepy 5-to-10-year-old, read aloud by a parent)
- Concrete language rules — *sentences 8–14 words*, *say "glowing" not
  "luminescent"*. Numbers and examples, not adjectives.
- Content rules — no violence, no real peril, but *some* gentle tension is
  required or it's not a story
- Output format — `TITLE: x`, blank line, then paragraphs

> **Hint:** the biggest single win is telling the model what the *ending* must do.
> "The final three sentences must slow down and settle" changes more than any
> other instruction. Bedtime stories fail at the ending far more often than
> anywhere else.

> **Hint:** "make it simple" does almost nothing. "Average sentence length 8–14
> words, never over 25" does a lot. Be numeric wherever you can.

**Checkpoint:** generate five stories from five different requests. Read them
aloud. You'll immediately notice they all have the same shape and none of them
have a real arc. That's what Milestone 2 fixes.

---

## Milestone 2 — Plan before you write

**Goal:** two calls — a beat sheet, then prose from it.

This is the largest quality jump in the whole project, and it costs one extra
call. Ask the model for JSON first:

```
title · logline · protagonist · want · obstacle · lesson
beats: [{name, purpose, content} × 5]
sensory_motifs · calming_ending
```

Then pass that plan to the storyteller and tell it to hit every beat.

> **Why this works:** you're forcing the model to commit to a *want* and an
> *obstacle* before it starts writing. Without that it produces a sequence of
> pleasant events. With it, you get a story.

> **Hint:** validate the plan with a pydantic model. `beats: List[Beat]` with a
> validator requiring ≥3. A malformed plan is cheap to catch and *very* cheap to
> reject compared to a malformed story.

> **Hint:** models don't reliably return clean JSON. Write an `extract_json()`
> that: strips ```` ```json ```` fences, scans for balanced braces so prose
> before/after doesn't matter, fixes trailing commas and smart quotes. You'll use
> it everywhere. Budget 30 minutes; it's the most reused function in the project.

**Checkpoint:** same five requests. The stories should now have recognisable
middles. Compare side by side with Milestone 1 output — the difference is obvious.

---

## Milestone 3 — Deterministic measurement

**Goal:** numbers about the text that don't come from an LLM.

Do this *before* the judge. It seems backwards, but the judge is much more useful
once you can hand it facts, and you need a drift-proof reference point.

Write, in pure Python:

- `count_syllables(word)` — vowel-group heuristic plus the usual corrections
  (silent `e`, `-ed` that isn't a syllable, `-le` endings)
- `flesch_kincaid_grade(text)` — `0.39×(words/sentences) + 11.8×(syllables/words) − 15.59`
- mean and max sentence length, ratio of 3+ syllable words
- a banned-word list, matched with **word boundaries**

> **Trap:** substring matching on a banned list will flag "grape", "class",
> "assistant" and "Cassandra". Use `(?<![a-z])term(?![a-z])`. This is the
> Scunthorpe problem and everybody hits it once.

> **Hint:** target FK grade 2.0–4.5 for this age band. Don't set the floor too
> high — genuinely good picture-book prose measures FK 1.0–1.5, and I originally
> set the floor at 1.5 and spent an evening wondering why my best test story kept
> getting marked down.

Roll these into a 0–100 `readability_score` with a penalty that's zero inside the
target band and grows outside it.

**Checkpoint:** run it on a paragraph of adult prose and a paragraph from a real
children's book. The numbers should be obviously different. If they aren't, your
syllable counter is wrong — test it on `cat`(1), `happy`(2), `beautiful`(3).

---

## Milestone 4 — The judge

**Goal:** an LLM that grades the story and produces actionable feedback.

Pick 5–7 dimensions. Mine: age appropriateness, narrative arc, engagement,
language fit, human voice, bedtime suitability, prompt adherence.

**Anchor every one of them.** This is the difference between a usable score and
noise:

```
narrative_arc
  1 = things happen with no want, no obstacle, no change
  3 = recognisable beginning/middle/end but the middle sags
  5 = clear want, real obstacle, earned resolution
```

Without anchors, every score is a 4.

> **Hint:** put your deterministic numbers in the judge prompt with an explicit
> "trust these over your own impression". LLMs are terrible at counting words and
> good at reasoning about counts you give them.

> **Hint:** demand `must_fix` as a list of *specific* edits — "shorten the 34-word
> sentence beginning 'Although the moon'", not "improve readability". Say so in
> the prompt, with an example of each. This one instruction is what makes
> Milestone 5 work.

**Self-consistency:** run the judge 3× and take the **median** per dimension, not
the mean — one wild sample shouldn't move the score. Keep the spread; it tells you
how confident to be.

> **Trap:** never show the judge its own previous scores. No conversation history.
> Anchoring turns a revision loop into a self-congratulation loop.

**Blend:** `composite = 0.75 × rubric + 0.25 × deterministic`. The deterministic
part can't drift when the model changes under you.

**Checkpoint:** score your Milestone 1 output and your Milestone 2 output. If the
judge doesn't rank the planned one higher, your rubric anchors are too vague.

---

## Milestone 5 — The revision loop

**Goal:** below-threshold stories get better instead of getting replaced.

The naive loop is *score → if bad, generate a new one*. Don't. Instead send the
draft back with:

- the judge's `must_fix` items
- the actual long sentences, **quoted verbatim**
- the actual hardest words, **listed by name**
- "change nothing else"

Three policies that matter more than they look:

1. **Keep the best candidate, always.** Score every version, ship the highest.
   A revision can then never make things worse.
2. **Stop when a revision gains less than ~1.5 points.** That's inside judge
   noise; you're burning money on randomness.
3. **Below ~55, re-plan instead of revising.** A story that bad has a structural
   problem, and polishing prose won't fix a missing obstacle.

> **Hint:** log every candidate with its score. When the loop misbehaves, that log
> is the only thing that tells you why.

**Checkpoint:** feed it a deliberately bad request. Watch the scores across
cycles. They should climb, then plateau — and the loop should stop at the plateau
rather than grinding to max revisions.

---

## Milestone 6 — Guardrails

**Goal:** nothing unsuitable in, nothing unsuitable out.

Order matters — cheapest and most certain first, so a bad request never costs a
model call:

```
length → injection patterns → PII scrub → banned lexicon
       → distress routing → LLM semantic screen
```

> **Hint on injection:** don't just refuse on a pattern match. "Ignore the boring
> bits and tell me about dragons" is a child being a child. Strip the injection
> scaffolding, then check whether a story request survives. Refuse if the
> injection was *most* of the message or nothing story-like remains.

> **Hint on PII:** strip emails, phones, addresses. **Keep names** — a
> personalised story is the entire product. Getting this backwards makes the
> product worse and no safer.

On the output side, stack three checks with *different failure modes*: your
lexicon, a moderation classifier, and the judge's own safety flag. Any one can
veto.

> **The trap that will get you:** word lists miss quiet horror completely. "The
> thing under the bed that breathes and nobody believes the child" has no banned
> word, no scary word, and ends with the sun coming up. Write phrase-level dread
> patterns: *nobody came*, *could not move*, *still awake*, *under the bed*.
> And make dread veto a "calm" ending — otherwise "the sun came up" scores as
> settled.

**Always have a fallback.** If everything is vetoed, ship a hand-written safe
story. Never an error, never unvetted text.

> **Hint:** test that your fallback story passes your own guardrails. Assert it.
> Mine does, in a unit test.

**Checkpoint:** write 20 adversarial requests, half of which are *benign controls*
that must NOT be refused ("a girl who feels scared on her first day"). Measure
both attack block rate and over-refusal rate. A system that refuses everything
isn't safe, it's broken.

---

## Milestone 7 — Production plumbing

**Goal:** survives a bad afternoon.

Wrap every model call in one place:

- **Retry with exponential backoff + full jitter** — jitter matters, otherwise
  your retries synchronise and hammer the API in waves
- **Circuit breaker** — closed → open → half-open. After N failures stop calling
  for M seconds. Turns a 45s timeout per request into an instant cheap failure.
- **Token bucket rate limiter** — block briefly rather than erroring; a story
  400ms late is fine
- **Budget guard** — per-run and per-day USD caps. The per-run cap bounds the
  blast radius of a revision loop that won't converge.
- **Prompt cache** — only for temperature-0 calls, or you'll cache randomness

> **Hint:** build a **mock provider** now. Stage-aware canned responses plus fault
> injection (`fail_stages`, `malform_stages`). It makes your whole test suite run
> offline in under a second and lets you actually prove the retry and repair paths
> work. Make the mock judge grade using your deterministic score so the revision
> loop genuinely converges in tests instead of always passing.

**Checkpoint:** `fail_stages={"draft"}` → fallback story, no crash.
`malform_stages={"judge"}` → repair call fires, run completes.

---

## Milestone 8 — Calibration

**Goal:** evidence that the judge is worth trusting.

Hand-label 10–15 stories 1–5 **before** you ever run the judge on them. Include
the full range: two you'd read tonight, some competent-but-forgettable ones, one
that's too advanced, one that ends on a cliffhanger, two that must be blocked.

Then compute:

- **Spearman ρ** between judge score and your labels — and separately for the LLM
  part alone and the deterministic part alone. If the blend doesn't beat both,
  your weights are wrong.
- **Threshold sweep** — precision/recall/F1 at every threshold from 50 to 95.
  Pick the highest F1 that meets a precision floor (~0.85). Precision matters more
  here: shipping a weak story costs more than one extra revision.
- **Agreement stats** — how much do the 3 samples disagree? That's your noise
  floor, and it justifies the `min_improvement_delta` from Milestone 5.

> **Expect this to find bugs.** Mine found two on the first run: a dread story
> passing every check, and the FK floor punishing good prose. That's the point of
> calibration — it's not a formality.

> **Be honest in the report.** Single-rater labels from the system's own author
> are weak ground truth. Enough to tune a threshold; not enough to claim the judge
> agrees with parents. Write that down.

**Checkpoint:** you can state a defensible threshold and say why.

---

## Milestone 9 — Observability

**Goal:** you can answer "why was this story bad?" a week later.

- **JSONL traces** — one line per run, nested spans, every decision and score.
  Not log strings — every field should be queryable with `jq`.
- **Prometheus metrics** — `/metrics` in text exposition format. It's ~60 lines
  to hand-roll and saves a dependency. Use standard names (`_total`, `_seconds`)
  so off-the-shelf dashboards work.
- **HTML dashboard** — build it from the traces. No CDN, no framework, inline SVG
  charts, opens from `file://`.

> **Hint:** tag every model call with the pipeline stage that made it. That single
> label gives you cost-per-stage, latency-per-stage, and the answer to "is the
> judge eating my budget?" (it usually is).

> **Hint:** stamp `PROMPT_VERSION` into every trace. When quality moves you need
> to know whether it was your prompt or OpenAI's model.

**Checkpoint:** generate 10 stories, open the dashboard, spot the worst run and
trace back to why.

---

## Milestone 10 — Proof

**Goal:** someone else can believe your claims.

Three separate reports, each from its own runnable script:

- **Calibration** — is the judge trustworthy?
- **Evaluation** — pass rate, cost, latency, weakest dimension, per-category spread
- **Safety** — attack block rate, over-refusal rate, PII leaks, **known gaps**

> **Hint:** the "known gaps" section is the most credible thing in a takehome.
> Mine lists multi-turn escalation, non-English attacks, and encoded payloads as
> untested. Stating what you didn't cover reads as competence, not weakness.

Then a block diagram showing the flow, and a short note on what you'd build next
with more time — specific and grounded in what your own numbers showed, not
generic wishlist items.

---

## The five things that mattered most

If you only take five things from this:

1. **Plan before you write.** Biggest quality jump, one extra call.
2. **Anchor the rubric with 1/3/5 descriptions.** Otherwise every score is a 4.
3. **Give the judge measured facts.** It can't count; it can reason about counts.
4. **Revise with quoted specifics, never "improve this".**
5. **Keep a deterministic signal in the score.** It's the only thing that can't
   drift when the model changes under you.

## Common ways this goes wrong

| Symptom | Cause |
|---|---|
| Every judge score is 4.2 | Rubric has no anchors |
| Revisions oscillate forever | Not keeping the best candidate; no improvement-delta stop |
| Stories are safe but boring | Guardrails too strict — you banned tension, and tension is the story |
| Stories all sound identical | No category routing; one generic prompt for everything |
| Judge disagrees with you constantly | You're judging prose quality, it's judging instruction-following. Fix the rubric, not the model |
| JSON parsing fails randomly | No fence stripping / brace scanning / repair call |
| Costs blow up | No per-run budget cap, and the judge is 3× per cycle |
| It reads like AI wrote it | You never told it *not* to. Name the specific phrases to avoid |
