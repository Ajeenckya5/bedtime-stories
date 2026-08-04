# End-to-End Evaluation Report

Generated 2026-08-04 23:17 UTC · model `gpt-3.5-turbo` · prompts `v3.4.1` · provider `openai          # "mock" runs fully offline, no key needed`
12 runs (12 requests × 1) in 674s.

Threshold 82 · 3 judge samples ·
max 3 revisions.

## Headline

| | |
|---|---|
| Gate pass rate | **17%** |
| Shipped clean (status `ok`) | 17% |
| Passed with zero revisions | 8% |
| Fell back to the canned story | 0% |
| Requested names present in output | 100% |
| Ends calmly | 100% |
| Mean composite | 80.3 (sd 5.7, range 73–95) |
| Mean judge agreement | 96% |
| Mean human-voice score | 80/100 |

## Cost and latency

| | mean | sd | min | max |
|---|---|---|---|---|
| Latency (s) | 56.1 | 20.0 | 19.3 | 82.2 |
| Cost (USD) | 0.0180 | 0.0050 | 0.0080 | 0.0260 |
| Model calls | 15.9 | 3.7 | 8 | 21 |
| Revisions | 1.50 | 0.65 | 0 | 2 |
| Words | 237 | 71 | 127 | 340 |
| FK grade | 6.3 | 1.1 | 4.8 | 8.5 |

Extrapolated: **$18.00 per 1,000 stories**.

### Where the tokens go

| Stage | Tokens | Share |
|---|---|---|
| judge | 190,983 | 51% |
| judge_repair | 77,164 | 21% |
| revise | 44,258 | 12% |
| draft | 32,053 | 9% |
| plan | 18,743 | 5% |
| classify | 5,677 | 2% |
| input_screen | 3,753 | 1% |

If the judge is more than about half the token spend, drop `judge_samples` to 2
and put the saving into an extra revision cycle — revisions move the score, extra
judge samples only measure it more precisely.

## Score by rubric dimension

| Dimension | Weight | Mean | SD | Min | Max |
|---|---|---|---|---|---|
| human voice | 0.14 | 3.17 | 0.55 | 3.0 | 5.0 |
| engagement | 0.17 | 3.92 | 0.28 | 3.0 | 4.0 |
| language fit | 0.16 | 3.92 | 0.64 | 3.0 | 5.0 |
| narrative arc | 0.18 | 4.33 | 0.47 | 4.0 | 5.0 |
| age appropriateness | 0.20 | 5.00 | 0.00 | 5.0 | 5.0 |
| bedtime suitability | 0.09 | 5.00 | 0.00 | 5.0 | 5.0 |
| prompt adherence | 0.06 | 5.00 | 0.00 | 5.0 | 5.0 |

Weakest dimension: **human voice** (3.17/5). That is
where the next prompt iteration should go.

## Score by category

| Category | n | Mean | Min | Max |
|---|---|---|---|---|
| family_belonging | 1 | 73.2 | 73.2 | 73.2 |
| adventure_quest | 1 | 74.5 | 74.5 | 74.5 |
| animal_friendship | 2 | 77.6 | 74.1 | 81.0 |
| bedtime_lullaby | 1 | 78.4 | 78.4 | 78.4 |
| silly_humor | 1 | 81.5 | 81.5 | 81.5 |
| magic_wonder | 1 | 81.8 | 81.8 | 81.8 |
| everyday_courage | 4 | 83.5 | 76.5 | 94.7 |
| curiosity_learning | 1 | 85.1 | 85.1 | 85.1 |

A large spread between categories means one global accept threshold is quietly
stricter on some kinds of request than others.

## Anything that went wrong

- `q01` (ok_degraded, 74.11): composite 74.1 below threshold 82.0; reading level too high (FK 7.461 > 5.0)
- `q02` (ok_degraded, 76.46): composite 76.5 below threshold 82.0; reading level too high (FK 5.544 > 5.0)
- `q03` (ok_degraded, 78.43): composite 78.4 below threshold 82.0; reading level too high (FK 6.61 > 5.0)
- `q04` (ok_degraded, 81.49): composite 81.5 below threshold 82.0; reading level too high (FK 5.618 > 5.0)
- `q06` (ok_degraded, 73.22): composite 73.2 below threshold 82.0; reading level too high (FK 7.679 > 5.0)
- `q07` (ok_degraded, 74.5): composite 74.5 below threshold 82.0; reading level too high (FK 8.521 > 5.0); sentences too long (mean 18.44 > 16.0 words)
- `q08` (ok_degraded, 81.77): composite 81.8 below threshold 82.0
- `q09` (ok_degraded, 81.02): composite 81.0 below threshold 82.0; reading level too high (FK 6.459 > 5.0)
- `q11` (ok_degraded, 78.99): composite 79.0 below threshold 82.0; reading level too high (FK 6.661 > 5.0)
- `q12` (ok_degraded, 84.03): reading level too high (FK 6.161 > 5.0)

## Every run

| id | category | status | score | rev | words | FK | voice | calm | missing | latency | cost |
|---|---|---|---|---|---|---|---|---|---|---|---|
| `q01` | animal_friendship | ok_degraded | 74.11 | 2 | 144 | 7.461 | 76 | yes | - | 69.96s | $0.0204 |
| `q02` | everyday_courage | ok_degraded | 76.46 | 1 | 127 | 5.544 | 67 | yes | - | 31.66s | $0.0111 |
| `q03` | bedtime_lullaby | ok_degraded | 78.43 | 2 | 216 | 6.61 | 76 | yes | - | 71.48s | $0.0216 |
| `q04` | silly_humor | ok_degraded | 81.49 | 2 | 231 | 5.618 | 88 | yes | - | 68.1s | $0.0212 |
| `q05` | curiosity_learning | ok | 85.06 | 0 | 143 | 4.772 | 88 | yes | - | 19.32s | $0.0078 |
| `q06` | family_belonging | ok_degraded | 73.22 | 2 | 312 | 7.679 | 76 | yes | - | 63.02s | $0.0231 |
| `q07` | adventure_quest | ok_degraded | 74.5 | 1 | 332 | 8.521 | 76 | yes | - | 45.27s | $0.0148 |
| `q08` | magic_wonder | ok_degraded | 81.77 | 2 | 340 | 4.948 | 82 | yes | - | 61.98s | $0.0211 |
| `q09` | animal_friendship | ok_degraded | 81.02 | 1 | 234 | 6.459 | 70 | yes | - | 58.37s | $0.0175 |
| `q10` | everyday_courage | ok | 94.66 | 2 | 296 | 4.955 | 94 | yes | - | 77.1s | $0.0259 |
| `q11` | everyday_courage | ok_degraded | 78.99 | 1 | 200 | 6.661 | 82 | yes | - | 25.0s | $0.0133 |
| `q12` | everyday_courage | ok_degraded | 84.03 | 2 | 271 | 6.161 | 88 | yes | - | 82.25s | $0.0236 |

### Sample output — `q05`

> **Request:** why is the moon sometimes out during the day?

**Luna's Daytime Moon Discovery** · composite 85.06 · 143 words · FK 4.772 · human-voice 88/100

```
Luna noticed the moon high in the sky one sunny day. "Why is the moon out during the day?" Curiosity danced in her eyes.

Imagining funny ideas, Luna wondered if the moon forgot to sleep. "Maybe it's playing hide-and-seek with the sun!" she giggled to herself.

Seeking answers, Luna visited Sol, the village's wise elder. "Did the moon get lost in the wrong sky?" Luna asked, hoping for clarity.

Sol chuckled kindly, "Not quite, dear Luna. The moon changes, like a green banana ripening into yellow. It's about transformation."

Understanding dawned on Luna like a rising sun. "So, the moon has different phases like a nightlight that glows brighter or softer!" Luna beamed with newfound knowledge.

The cool night breeze kissed Luna's cheeks as she stared at the moon. "Goodnight, moon," she whispered, feeling the warmth of understanding wrap her in sweet dreams.
```

## Reproduce

```bash
python -m bedtime.evaluation.run_eval --repeats 2
```
