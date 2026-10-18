# Benchmark results

Run on 2026-10-18. Model `openai/gpt-oss-120b` via Groq free tier, temperature 0. Catalogue snapshot `85454b7fb8120f48`. Five tasks. Every configuration ends with at least one real simulation per task; pass means the simulator printed the task's expected output.

## Summary

| Config | Grounding | Retries on | Passed | Pass rate | Mean attempts (on pass) | Simulated seconds | Tokens in / out |
|---|---|---|---|---|---|---|---|
| A | no | nothing | 1/5 | 20% | 1.0 | 5 | 4935 / 5814 |
| B | yes | nothing | 3/5 | 60% | 1.0 | 18 | 11620 / 6248 |
| C | yes | schema, lint, compile, consistency | 3/5 | 60% | 1.33 | 23 | 20229 / 9131 |
| D | yes | everything incl. simulation | 5/5 | 100% | 1.6 | 29 | 23176 / 9902 |

## Per task

| Task | A | B | C | D |
|---|---|---|---|---|
| T01_blink | fail at lint | pass | pass | pass |
| T02_button_serial | fail at lint | fail at compile | fail at compile (3) | pass (3) |
| T03_servo_sweep | fail at schema | pass | pass | pass |
| T04_ultrasonic_distance | pass | fail at compile | pass (2) | pass (2) |
| T05_rgb_cycle | fail at lint | pass | fail at simulate | pass |

Numbers in brackets are attempts used.

## What the numbers say

- Without the catalogue (A) the model invents pin names and part attributes. Three of four failures were caught by lint before any simulation time was spent.
- The catalogue alone (B) takes it from 1 to 3 of 5. Grounding is the single biggest lever on this model.
- Retrying on free-check errors (C) rescued T04 (a compile error fixed on attempt 2) but did not change the total: T05 passed every free check and then failed in simulation, and C has no way to see that. T02 failed compile three times in a row with the same mistake, `static void setup()`, which the model did not correct from the error text.
- Retrying on simulation errors as well (D) passed all five. T02 took three attempts and T04 took two.

## Caveats, read these before quoting the table

- Five tasks. Each one is 20 percentage points. This is a pilot, not a result with intervals. The suite is being extended.
- Temperature 0 on a hosted model is not deterministic. C and D are separate runs, so some of the C to D gap is sampling noise, not only the extra feedback. T05 passing first time in D and failing in C is an example.
- All tasks are single-board, Arduino framework, catalogue-only parts. Nothing here says anything about harder designs.
- Gemini's free tier allowed 20 requests per day on the model tested, which was not enough for a four-configuration sweep. The sweep moved to Groq. The two earlier Gemini runs in `docs/demo-runs.md` are on a different model and are not comparable to this table.

## Reproducing

```
export WOKWI_CLI_TOKEN=wok_...  GROQ_API_KEY=gsk_...
for c in A B C D; do circuitmind bench $c --provider groq; done
```

Each run writes `benchmark/results/<config>.json` with per-task rows and `runs/bench/<stamp>/` with every attempt's prompt reply, design, diagram, firmware and feedback.
