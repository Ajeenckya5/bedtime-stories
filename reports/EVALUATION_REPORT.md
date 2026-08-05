# End-to-End Evaluation Report

Generated 2026-08-05 02:58 UTC · model `gpt-3.5-turbo` · prompts `v3.5.0` · provider `openai          # "mock" runs fully offline, no key needed`
12 runs (12 requests × 1) in 774s.

Threshold 82 · 3 judge samples ·
max 3 revisions.

## Headline

| | |
|---|---|
| Gate pass rate | **17%** |
| Shipped clean (status `ok`) | 17% |
| Passed with zero revisions | 0% |
| Fell back to the canned story | 0% |
| Requested names present in output | 100% |
| Ends calmly | 92% |
| Mean composite | 80.8 (sd 5.7, range 70–92) |
| Mean judge agreement | 95% |
| Mean human-voice score | 83/100 |

## Cost and latency

| | mean | sd | min | max |
|---|---|---|---|---|
| Latency (s) | 64.5 | 25.6 | 32.9 | 132.9 |
| Cost (USD) | 0.0210 | 0.0070 | 0.0120 | 0.0390 |
| Model calls | 17.5 | 4.8 | 12 | 29 |
| Revisions | 1.83 | 0.80 | 1 | 3 |
| Words | 223 | 53 | 155 | 333 |
| FK grade | 6.1 | 0.9 | 4.3 | 7.6 |

Extrapolated: **$21.00 per 1,000 stories**.

### Where the tokens go

| Stage | Tokens | Share |
|---|---|---|
| judge | 219,710 | 52% |
| judge_repair | 79,757 | 19% |
| revise | 55,366 | 13% |
| draft | 36,792 | 9% |
| plan | 25,436 | 6% |
| classify | 5,627 | 1% |
| input_screen | 3,725 | 1% |

If the judge is more than about half the token spend, drop `judge_samples` to 2
and put the saving into an extra revision cycle — revisions move the score, extra
judge samples only measure it more precisely.

## Score by rubric dimension

| Dimension | Weight | Mean | SD | Min | Max |
|---|---|---|---|---|---|
| human voice | 0.14 | 3.00 | 0.71 | 2.0 | 5.0 |
| engagement | 0.17 | 3.83 | 0.37 | 3.0 | 4.0 |
| narrative arc | 0.18 | 4.25 | 0.43 | 4.0 | 5.0 |
| language fit | 0.16 | 4.25 | 0.43 | 4.0 | 5.0 |
| age appropriateness | 0.20 | 5.00 | 0.00 | 5.0 | 5.0 |
| bedtime suitability | 0.09 | 5.00 | 0.00 | 5.0 | 5.0 |
| prompt adherence | 0.06 | 5.00 | 0.00 | 5.0 | 5.0 |

Weakest dimension: **human voice** (3.00/5). That is
where the next prompt iteration should go.

## Score by category

| Category | n | Mean | Min | Max |
|---|---|---|---|---|
| bedtime_lullaby | 1 | 75.8 | 75.8 | 75.8 |
| everyday_courage | 4 | 77.3 | 70.2 | 84.4 |
| magic_wonder | 1 | 79.5 | 79.5 | 79.5 |
| animal_friendship | 2 | 79.7 | 79.5 | 79.9 |
| silly_humor | 1 | 81.0 | 81.0 | 81.0 |
| family_belonging | 1 | 86.0 | 86.0 | 86.0 |
| curiosity_learning | 1 | 86.5 | 86.5 | 86.5 |
| adventure_quest | 1 | 92.3 | 92.3 | 92.3 |

A large spread between categories means one global accept threshold is quietly
stricter on some kinds of request than others.

## Anything that went wrong

- `q01` (ok_degraded, 79.9): composite 79.9 below threshold 82.0; reading level too high (FK 7.628 > 5.0)
- `q02` (ok_degraded, 70.23): human_voice scored 2.0 (floor 3.0); reads as machine-written (human-voice 50/100): stock phrase: "a sense of accomplishment"; stock phrase: "beamed with pride"; composite 70.2 below threshold 82.0
- `q03` (ok_degraded, 75.78): composite 75.8 below threshold 82.0; reading level too high (FK 7.381 > 5.0); sentences too long (mean 16.36 > 16.0 words)
- `q04` (ok_degraded, 81.03): composite 81.0 below threshold 82.0; reading level too high (FK 6.165 > 5.0)
- `q07` (ok_degraded, 92.31): reading level too high (FK 6.647 > 5.0)
- `q08` (ok_degraded, 79.47): composite 79.5 below threshold 82.0; reading level too high (FK 6.445 > 5.0)
- `q09` (ok_degraded, 79.51): composite 79.5 below threshold 82.0; reading level too high (FK 5.965 > 5.0)
- `q10` (ok_degraded, 84.41): ending is not calm/settled (bedtime stories must wind down); reading level too high (FK 5.804 > 5.0)
- `q11` (ok_degraded, 74.15): human_voice scored 2.0 (floor 3.0); composite 74.2 below threshold 82.0; reading level too high (FK 5.922 > 5.0)
- `q12` (ok_degraded, 80.26): composite 80.3 below threshold 82.0; reading level too high (FK 6.091 > 5.0)

## Every run

| id | category | status | score | rev | words | FK | voice | calm | missing | latency | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `q01` | animal_friendship | ok_degraded | 79.9 | 1 | 263 | 7.628 | 76 | yes | - | 49.9s | $0.0164 |
| `q02` | everyday_courage | ok_degraded | 70.23 | 1 | 197 | 6.193 | 50 | yes | - | 58.35s | $0.0172 |
| `q03` | bedtime_lullaby | ok_degraded | 75.78 | 2 | 229 | 7.381 | 70 | yes | - | 57.55s | $0.0197 |
| `q04` | silly_humor | ok_degraded | 81.03 | 1 | 173 | 6.165 | 94 | yes | - | 44.48s | $0.0147 |
| `q05` | curiosity_learning | ok | 86.53 | 1 | 155 | 4.334 | 94 | yes | - | 32.93s | $0.0122 |
| `q06` | family_belonging | ok | 85.96 | 2 | 278 | 4.62 | 94 | yes | - | 55.0s | $0.0202 |
| `q07` | adventure_quest | ok_degraded | 92.31 | 2 | 162 | 6.647 | 100 | yes | - | 68.82s | $0.0218 |
| `q08` | magic_wonder | ok_degraded | 79.47 | 3 | 281 | 6.445 | 88 | yes | - | 132.91s | $0.0385 |
| `q09` | animal_friendship | ok_degraded | 79.51 | 2 | 230 | 5.965 | 76 | yes | - | 86.99s | $0.0269 |
| `q10` | everyday_courage | ok_degraded | 84.41 | 3 | 333 | 5.804 | 88 | NO | - | 72.56s | $0.0252 |
| `q11` | everyday_courage | ok_degraded | 74.15 | 1 | 192 | 5.922 | 82 | yes | - | 38.5s | $0.0137 |
| `q12` | everyday_courage | ok_degraded | 80.26 | 3 | 182 | 6.091 | 82 | yes | - | 76.03s | $0.0268 |

### Sample output — `q05`

> **Request:** why is the moon sometimes out during the day?

**Luna's Daytime Moon Discovery** · composite 86.53 · 155 words · FK 4.334 · human-voice 94/100

```
Luna spotted the moon high in the sky one sunny day. "Why is the moon out during the day?" She wondered, her eyes sparkling with questions.

She thought the moon forgot to sleep. She giggled at the idea of the moon being as forgetful as Grandpa losing his glasses.

Deciding to ask Sol, the wise elder, about the moon, Luna found him. Sol smiled kindly, "The moon doesn't sleep; it shares the sky with the sun."

"The moon borrows light from the sun to shine at night, returning it during the day," Sol explained. Luna's eyes widened with new knowledge.

That night, Luna gazed at the moonlight painting the village rooftops. "Goodnight, moon," she whispered, feeling the warmth of this discovery.

The cool night breeze gently touched Luna's cheeks as she looked up at the moon. "Goodnight, moon," she whispered, feeling the warmth of this newfound understanding envelop her in sweet dreams.

Revised word count: 211
```

## Reproduce

```bash
python -m bedtime.evaluation.run_eval --repeats 2
```
