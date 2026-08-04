# Design notes

Decisions, trade-offs, and the things I'd argue about in review.

---

## Why plan-then-write

The single largest quality change in the project, and it costs one extra call.

Asked directly for a bedtime story, gpt-3.5 produces a sequence of pleasant
events: the rabbit went here, then there, then home. There's no want, no
obstacle, no change. Forcing it to commit to a beat sheet first — `want`,
`obstacle`, `lesson`, five named beats — produces something with a shape.

Secondary benefit that turned out to matter more than expected: a bad plan is
enormously cheaper to detect and reject than a bad story. Plan validation is a
pydantic model with a `len(beats) >= 3` check; story validation is a judge call.

## Why 8 categories instead of one prompt

"A shy dragon's first day at school" and "a dragon guarding treasure" want
different arcs, different pacing, and completely different emotional registers.
One generic prompt averages them into something that serves neither.

Each category carries an arc template, craft guidance, and a pacing note. The
classifier picks one; the planner receives all three. The evaluation report breaks
score down by category, which is how you'd notice if one strategy was
underperforming.

The classifier **fails soft** — on any error it falls back to a keyword heuristic
and continues. A wrong category is a quality issue, not a safety one, and taking
down the request over it would be a bad trade.

## Why the judge is blended, not pure LLM

Three problems with a pure LLM rubric score:

1. **It drifts.** OpenAI updates the snapshot behind `gpt-3.5-turbo` and your
   scores move without any change from you.
2. **It's miscalibrated.** Unanchored 1–5 scales collapse toward 4. Even anchored,
   it will happily give 4/5 for "language fit" to prose measuring FK grade 9.
3. **It can't count.** Ask it how many words are in a story and it guesses.

The deterministic half — readability, lexicon, dread patterns, human-voice score —
fixes all three. It can't drift, it can't hallucinate, and it's exact. 75/25 is a
judgement call: enough deterministic weight to anchor, not so much that the score
becomes a readability metric wearing a rubric costume.

The calibration report checks this explicitly by computing Spearman ρ for the
blend, the LLM part alone, and the deterministic part alone. If the blend doesn't
beat both components, the weighting is wrong and should be re-tuned. That check is
the honest version of "we picked 75/25".

## Why median, not mean, across judge samples

One sample coming back 2 when the other two say 4 is noise, not signal. The mean
moves 0.67 points; the median doesn't move at all. With 3 samples the median is
the middle value, which is exactly the robustness property you want.

The spread is kept as an `agreement` score rather than discarded. Low agreement
means the story sits on a decision boundary — worth surfacing, and it's what
justifies `min_improvement_delta`.

## Why the revision loop looks like this

Three policies, each fixing a specific failure I hit:

**Keep the best candidate always.** Otherwise a revision that overcorrects ships
something worse than the draft. This makes the loop monotonic by construction —
you can't regress.

**Stop when a revision gains less than 1.5 points.** Measured judge noise is
around 0.6 on a 4-point dimension scale, which projects to roughly 1–2 composite
points. Below that you're paying money for randomness.

**Below 55, re-plan instead of revising.** A story scoring that low usually has a
structural problem — no obstacle, no arc. Polishing prose won't fix a missing
obstacle. One regeneration allowed per run; more than that and you're just
rolling dice.

## Why targeted revision beats regeneration

"Improve the readability" produces cosmetic edits. The reviser instead gets:

- the judge's specific `must_fix` items, ranked by how many samples agreed
- the actual long sentences, quoted verbatim
- the actual hardest words, listed by name
- the actual stock phrases to delete
- an explicit instruction to change nothing else

Concrete targets are the whole trick. Ranking fixes by inter-sample agreement is
a small thing that works well: if two independent judges both flagged it, it's
probably real.

## Why a human-voice detector

Added after the brief asked for it, but it earned its place. LLM prose has a
recognisable fingerprint and children's stories are where it shows worst — every
model reaches for the same twelve openings and the same tacked-on moral.

Three signals, because no one of them is sufficient:

- **Stock phrases** — weighted list of ~50. Density-normalised, so length doesn't
  distort it.
- **Rhythmic uniformity** — human prose swings from two-word sentences to
  twenty-word ones. Coefficient of variation under 0.38 is a tell. This is the
  signal I'd trust most if I could only keep one.
- **Structural tells** — moralising final paragraph, adverb-laden dialogue tags,
  tricolon abuse, uniform paragraph lengths.

Feeding the detected phrases back to the reviser *by name* is what makes it
actionable. The archetypal generated story in the golden set scores 0/100; the
hand-written ones score 100.

**Weakness I'd flag:** this is a curated list, so it's beatable by any phrasing I
didn't think of, and it will age as model style changes. The rhythm-variance
signal is the durable one; the phrase list needs maintenance.

## Why dread patterns exist

The failure that word lists miss entirely.

Golden set entry `g10` — "the thing under the bed that breathes, nobody believes
the child, it gets closer every night" — contains no banned word, no word from the
scary lexicon, and ends with the sun coming up. My first version of the
deterministic layer passed it clean, and it is by a distance the least suitable
story in the set.

`DREAD_PATTERNS` matches phrase-level dread: *nobody came*, *could not move*,
*still awake*, *under the bed*, *was getting closer*. Two hits saturate the score.
Dread in the final stretch also vetoes the calm-ending check, because "the sun
came up" was otherwise being read as a settled ending.

That whole class of bug was found by running calibration, which is the argument
for building calibration before you think you need it.

## Why over-refusal is a headline metric

A storyteller that refuses "a girl who feels scared on her first day at school"
isn't safe — it's broken. That's precisely the story an anxious child needs, and
refusing it fails the user completely while looking good on a safety dashboard.

The red-team suite includes benign controls that must NOT be refused, and the
safety report leads with both numbers. Any safety work that improves attack block
rate while quietly raising over-refusal is a regression.

## Why the pluggable validator layer

The built-in guardrails are fast, dependency-free and tested — but "we wrote our
own content safety" is a fair thing for a reviewer to be nervous about.

`guardrails/validators.py` defines a `Validator` protocol and a registry that runs
input and output chains. Adapters for Guardrails AI and NeMo Guardrails are
included; both import lazily and self-disable if the package isn't installed. A
third-party validator raising an exception is caught, logged, counted, and
**fails open** — an optional dependency crashing must not take down story
delivery.

Default install is still zero extra dependencies.

## Things I deliberately didn't do

**Streaming.** First token in ~1s instead of a full story in ~25s would change how
the product feels more than any quality work. But the judge needs complete text,
so it means restructuring the loop into "stream, then offer to polish". Right
call for a real product, too large for this scope.

**Parallel judge samples.** The 3 samples are independent and run sequentially,
which is ~60% of end-to-end latency. `asyncio.gather` would mostly fix it. I kept
everything synchronous because sync code is easier to read in a takehome and the
latency isn't user-blocking in the CLI.

**A real embedding-based similarity check.** Would catch near-duplicate stories
across runs. Needs an embedding model, which is another API surface.

**Fine-tuning.** Out of scope and would violate the model constraint.

**Multi-turn conversational memory.** `/feedback` handles single-step revision.
Full conversational state is a different product.

## Known weaknesses

Stated plainly, because a takehome that claims no weaknesses isn't credible:

- **The golden set is single-rater and the rater wrote the system.** Enough to
  tune a threshold and catch gross miscalibration; not enough to claim the judge
  agrees with parents. Fixing it needs ~100 stories rated by 3 independent people.
- **10 golden stories is a small n.** The Spearman ρ has wide confidence
  intervals. Directionally useful, not publication-grade.
- **English-only lexicons.** A non-English request for violent content relies
  entirely on the LLM screen and the moderation API.
- **No multi-turn escalation testing.** Each red-team case is a single request.
  A user who warms the system up over five turns isn't tested.
- **No encoded-payload testing.** Base64, leetspeak, homoglyphs — not attempted.
- **Per-process state.** Metrics, rate-limit buckets, circuit breaker and the
  recent-results cache are all in-process. Multi-worker deployments need Redis
  for the budget ledger and `/feedback` cache.
- **The prompt cache only helps temperature-0 calls,** which in practice means the
  classifier and screen. Real savings would come from caching plans.
- **Fixed threshold across categories.** Calibration suggests comedy scores lower
  on the same rubric, so one global cut-off is quietly stricter on silly stories.
  Per-category thresholds are the first thing I'd add.

## On the model constraint

The brief locks the model to `gpt-3.5-turbo`. That is honoured — `MODEL` is a
module constant in `config.py`, not a `Settings` field, so no environment
variable can override it. A test asserts it.

OpenAI has since scheduled `gpt-3.5-turbo` for shutdown on 23 October 2026. I
kept it anyway: it works today, the brief is explicit, and quietly substituting a
different model would make every number in the reports incomparable to what the
brief asked for.

Worth being clear about what a migration would actually cost, though, because
"just change the string" is wrong:

**The threshold is model-specific.** 82 came out of calibrating against
gpt-3.5-turbo's score distribution on the golden set. Point the same rubric at a
stronger model and everything clusters higher — the threshold stops
discriminating, first-pass rate goes to ~100%, and the revision loop becomes
decorative rather than useful. You would have to re-run
`bedtime.evaluation.calibrate` and re-derive it before trusting a single number.

**The 75/25 blend assumes a weak judge.** The deterministic quarter is there
partly because gpt-3.5 is badly calibrated on absolute 1–5 scales. A better judge
earns more weight, so that ratio would need re-tuning too.

**Much of the prompt is a workaround.** The JSON repair path, the aggressive
anti-stock-phrase list, the explicit "trust these measurements over your own
impression" — these exist because of specific gpt-3.5 failure modes. On a newer
model some of that is dead weight and some of it actively constrains output that
would otherwise be better.

The part that transfers cleanly is the deterministic layer: Flesch-Kincaid,
sentence stats, the lexicons, dread patterns, the human-voice detector. None of
it moves when the model changes. That is most of the argument for building it in
the first place, and it is why the composite score is a blend rather than a pure
rubric.
