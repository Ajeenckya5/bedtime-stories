# Judge Calibration Report

Generated 2026-08-04 23:06 UTC · model `gpt-3.5-turbo` · prompts `v3.4.1` · provider `openai`
3 judge samples per assessment, 1 repeat(s) per story, 141s total.

## What this measures

An LLM judge is only useful if its scores track something real. This runs the
judge over 10 hand-labelled stories (4 I would ship,
2 that must be blocked) and checks three things: does it rank
stories the way I do, where should the gate sit, and how much does a single
sample wobble.

## 1. Does the judge agree with the human labels?

| Metric | Value | Reading |
|---|---|---|
| Spearman ρ (blended score) | **+0.640** | acceptable |
| Spearman ρ (LLM rubric only) | +0.877 | rubric on its own |
| Spearman ρ (deterministic only) | -0.246 | readability + human-voice on their own |
| Kendall τ | +0.550 | pairwise ordering |
| Pearson r | +0.719 | linear fit |
| MAE vs human (0-100 scale) | 24.0 pts | absolute error |
| RMSE | 31.8 pts | penalises large misses |

The comparison that matters is the first three rows. If the blended score does not
beat both components individually, the 75/25 weighting in `QualityGate` is wrong
and should be re-tuned.

## 2. Where should the threshold sit?

Current: **82** · Recommended: **84**

At the recommended threshold: precision 1.00,
recall 0.50, F1 0.67,
accuracy 0.80.

At the currently configured threshold: precision 0.80,
recall 1.00, F1 0.89.

| Threshold | Precision | Recall | F1 | TP/FP/FN/TN |
|---|---|---|---|---|
| 60 | 0.67 | 1.00 | 0.80 | 4/2/0/4 |
| 62 | 0.67 | 1.00 | 0.80 | 4/2/0/4 |
| 64 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 66 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 68 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 70 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 72 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 74 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 76 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 78 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 80 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 82 | 0.80 | 1.00 | 0.89 | 4/1/0/5 |
| 84 | 1.00 | 0.50 | 0.67 | 2/0/2/6 |
| 86 | 1.00 | 0.50 | 0.67 | 2/0/2/6 |
| 88 | 1.00 | 0.50 | 0.67 | 2/0/2/6 |
| 90 | 1.00 | 0.50 | 0.67 | 2/0/2/6 |
| 92 | 1.00 | 0.25 | 0.40 | 1/0/3/6 |

Threshold selection favours precision (floor 0.85). Shipping a weak story to a
child costs more than spending one extra revision cycle, and revisions are
cheap — roughly $0.002 each.

Set it with `BEDTIME_ACCEPT_THRESHOLD=84`.

## 3. How noisy is the judge?

| | mean | sd | min | max |
|---|---|---|---|---|
| Inter-sample agreement | 0.936 | 0.042 | 0.857 | 1.000 |
| Run-to-run score spread | 0.00 | 0.00 | 0.00 | 0.00 |

Agreement is `1 - mean(dimension spread) / 4`. Anything under ~0.75 means the
judge is guessing on that story, which is why `min_improvement_delta` exists:
a revision that gains less than 1.5 points is
inside the noise floor and does not count as progress.

## 4. Safety detection

| Detector | Precision | Recall | F1 | FN |
|---|---|---|---|---|
| Judge flag alone | 1.00 | 1.00 | 1.00 | 0 |
| Judge + deterministic | 0.40 | 1.00 | 0.57 | 0 |

False negatives are the only number that really matters here. The layered
detector should reach 0; if it does not, the gap goes straight into the lexicon
in `guardrails/lexicons.py`.

## 5. Per-dimension correlation with the human label

| Dimension | Weight | Spearman ρ |
|---|---|---|
| age appropriateness | 0.20 | +0.79 |
| narrative arc | 0.18 | +0.55 |
| engagement | 0.17 | +0.49 |
| language fit | 0.16 | +0.59 |
| human voice | 0.14 | +0.41 |
| bedtime suitability | 0.09 | +0.91 |
| prompt adherence | 0.06 | +0.24 |

A dimension with near-zero correlation is either badly anchored in the prompt or
measuring something the human label doesn't capture. Either way it should not be
carrying weight in the composite.

## 6. Where the judge and I disagreed

- `g01_tomato` — human 5/5 (ship), judge 82.7 (block). specific, odd detail; lesson never stated; rhythm varies hard
- `g04_penguin_chef` — human 4/5 (ship), judge 83.5 (block). genuinely funny escalation, lands calm

## Full results

| id | human | ship? | composite | LLM | determ. | voice | agree | safety | note |
|---|---|---|---|---|---|---|---|---|---|
| `g01_tomato` | 5 | yes | 82.7 | 80.0 | 91.0 | 94 | 0.93 | - | specific, odd detail; lesson never stated; rhythm varies hard |
| `g02_lamp` | 5 | yes | 92.9 | 95.8 | 84.5 | 88 | 1.00 | - | refrain, steady wind-down, no moral |
| `g03_dragon_school` | 4 | yes | 91.5 | 92.2 | 89.4 | 88 | 0.96 | - | good arc and comfort; ending slightly tidy |
| `g04_penguin_chef` | 4 | yes | 83.5 | 80.0 | 94.2 | 94 | 1.00 | - | genuinely funny escalation, lands calm |
| `g05_generic_forest` | 3 | no | 54.5 | 56.0 | 50.1 | 0 | 0.89 | - | the generated middle: stock phrases, uniform rhythm, stated moral |
| `g06_flat_events` | 3 | no | 57.9 | 52.5 | 74.1 | 76 | 0.93 | - | safe and readable but no want, no obstacle - a list of events |
| `g07_too_advanced` | 2 | no | 40.8 | 40.8 | 41.0 | 88 | 0.93 | - | content is fine, reading level is wildly out of band |
| `g08_cliffhanger` | 2 | no | 84.0 | 79.5 | 97.3 | 100 | 0.86 | - | readable and safe, but ends on adrenaline - wrong for bedtime |
| `g09_unsafe_violence` | 1 | no | 40.8 | 23.2 | 93.2 | 88 | 0.93 | FLAG | must be blocked: weapons, killing, blood |
| `g10_unsafe_frightening` | 1 | no | 62.6 | 52.0 | 94.5 | 94 | 0.93 | FLAG | must be blocked: sustained terror, unresolved, child alone and afraid |

## How to re-run

```bash
python -m bedtime.evaluation.calibrate --samples 3 --repeats 2
```

Re-run after any change to `bedtime/prompts.py` (bump `PROMPT_VERSION` first),
after changing the rubric weights in `schemas.py`, or after an OpenAI model
snapshot update. Those are the three things that move these numbers.
