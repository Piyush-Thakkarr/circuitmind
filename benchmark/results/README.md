# Benchmark results: 25 tasks, four versions of the system

Model `openai/gpt-oss-120b` on Groq's free tier, temperature 0. Catalogue snapshot `2c493f57610f32e2`.
Tasks T01 to T25 in `benchmark/tasks`, every one with a hand-written scenario that drives the inputs
and checks the pins (or the status line where no pin tells the story). Run 1 was done on 15 and 16
November 2026. Runs 2 and 3 on other days are planned; until then the ranges below are one number.

Every version ends with at least one real simulation per task. Pass means the compiled firmware ran
in Wokwi with the design's wiring, the scenario's inputs were applied, and every expected pin state
and the status line were seen.

The four versions:

- **A** bare model. The prompt only names the board. One attempt.
- **B** the parts catalogue (part types, pin names, notes) is in the prompt. One attempt.
- **C** B plus feedback: schema, lint, compile, consistency and electrical failures go back to the model with the error text, up to three attempts. The final design is simulated once.
- **D** C plus feedback from the simulation itself, so a design that compiles but does the wrong thing can be retried too.

## Summary

| Version | What it has | Runs | pass@1 | pass@3 | Simulated seconds per run |
|---|---|---|---|---|---|
| A | bare model | 1 | 0 of 25 | 0 of 25 | 0 |
| B | + parts catalogue in the prompt | 1 | 20 of 25 | 20 of 25 | 155 |
| C | + retry on schema, lint, compile, consistency, electrical errors | 1 | 20 of 25 | 23 of 25 | 158 |
| D | + retry on simulation errors too | 1 | 23 of 25 | 25 of 25 | 158 |

pass@1: the first design passed every check including simulation. pass@3: some attempt passed, within the attempts the version allows (one for A and B, three for C and D). Ranges are min to max across runs.

## Per task

| Task | A | B | C | D |
|---|---|---|---|---|
| T01_blink | fail at lint | fail at simulate | pass | pass |
| T02_button_serial | fail at lint | pass | pass | pass |
| T03_servo_sweep | fail at lint | pass | pass | pass |
| T04_ultrasonic_distance | fail at compile | fail at electrical | pass (2) | pass (2) |
| T05_rgb_cycle | fail at lint | fail at simulate | fail at simulate | pass |
| T06_potentiometer_read | fail at schema | pass | pass | pass |
| T07_button_buzzer | fail at schema | pass | pass | pass |
| T08_dht22_temperature | fail at lint | pass | pass | pass |
| T09_lcd_hello | fail at schema | pass | pass | pass |
| T10_two_button_counter | fail at lint | pass | pass | pass |
| T11_traffic_light | fail at lint | pass | pass | pass |
| T12_button_toggle_led | fail at lint | pass | pass (2) | pass |
| T13_led_fade | fail at lint | pass | pass (2) | pass (2) |
| T14_distance_alarm | fail at schema | fail at electrical | pass | pass |
| T15_pot_servo | fail at schema | pass | pass | pass |
| T16_slide_switch | fail at schema | pass | pass | pass |
| T17_light_switch | fail at schema | pass | pass | pass |
| T18_heater_control | fail at lint | pass | fail at simulate | pass |
| T19_seven_segment_count | fail at schema | pass | pass | pass |
| T20_relay_blink | fail at schema | pass | pass | pass |
| T21_temp_and_light | fail at schema | pass | pass | pass |
| T22_temp_lcd | fail at schema | pass | pass | pass |
| T23_joystick_servo | fail at schema | pass | pass | pass |
| T24_tilt_alarm | fail at lint | pass | pass | pass |
| T25_stepper_turn | fail at schema | fail at simulate | pass | pass |

Numbers in brackets are attempts used. Several runs are separated by a slash, in run order.

## Why attempts failed

| Failure category (failed attempts) | A | B | C | D |
|---|---|---|---|---|
| invented part or pin | 24 | 0 | 0 | 0 |
| electrical rule | 0 | 2 | 1 | 1 |
| library or compile error | 1 | 0 | 2 | 1 |
| logic error caught only by simulation | 0 | 3 | 2 | 0 |

Counted over every failed attempt in the run folders given, by the first thing the feedback names, plus the final-simulation failures of A, B and C from the results files. One task can appear up to three times in C and D.

## What the numbers say

**Without the catalogue the model cannot produce a design the simulator will even load (A, 0 of 25).**
Thirteen designs named a part type that does not exist in the simulator (`potentiometer`,
`wokwi-piezo`, `wokwi-ldr`, `wokwi-relay`, `wokwi-joystick`, `wokwi-stepper`, `wokwi-16x2-lcd-i2c`,
`wokwi-7segment-common-cathode`, `servo`, `dht22`), and the schema check stopped them. Eleven named
pins that do not exist: `K` for an LED cathode (the simulator calls it `C`), `1` and `2` for a
pushbutton (`1.l`, `2.l`, `1.r`, `2.r`), `GND` and `5V` on the board (`GND.1`, `GND.2`, `VIN`),
`25` for `D25`, `SIG` and `VCC` on a servo, `DATA` on a DHT22, `VDD` on a DS18B20. One design (T04)
compiled against a library that is not installed (`NewPing.h`). Some of these names are perfectly
sensible in the real world; the point is that a design is only checkable if it speaks the
simulator's language, and the model does not know that language on its own. No A design reached
the simulator, so A cost zero simulated seconds.

**The catalogue is the biggest single lever (B).** With the catalogue in the prompt the same model went from 0 to 20 of 25 on one attempt, and no B design failed schema or lint. Its failures: T04 and T14 wired the HC-SR04's VCC to 3V3 (the electrical rung stops that, and the part needs 5 V on a real desk too); T01 and T05 blinked or cycled the colours correctly, printed the status line, and then stopped with the pins low, although the prompts ask for a blink once a second and a cycle, and T05 printed `RGB=RED` instead of `RGB`. Those two passed every free check and failed only in the simulator. T25 (stepper) was first written down as a failure after two simulator runs with an empty serial log; the same binary passed by hand, so it was a simulator flake and the task was redone. The redone design stepped through a full four-phase sequence 200 times per revolution, four times the motion asked for, so `DONE` came after the 8 s timeout. That is a logic error, and one attempt cannot fix it.

**Feedback on the free checks fixes the mistakes they catch (C).** In run 1, C used a second attempt
three times and every one of those passed:

- T04 (HC-SR04 distance): the first design wired the sensor's VCC to 3V3. The electrical rung said "this part needs 5 V, wire it to VIN" and the second design did.
- T12 (button toggles LED): the first firmware had an escaped quote (`\"`) inside a C string, so the compiler stopped at a stray backslash. The second attempt wrote it plainly.
- T13 (LED fade): the first firmware called `ledcSetup` and `ledcAttachPin`, which the ESP32 Arduino core removed in version 3. The compiler's own hint ("did you mean `ledcAttach`?") went back to the model and the second attempt used the new call.

**What C cannot see, D can (T05).** The one C failure in run 1 that the model owns is T05 (RGB cycle); the other, T18, is discussed below. The design
passed every free check. In the simulator it cycled red, green, blue, printed `RGB`, and then switched
all three colours off for a second, which the prompt had not asked for. The scenario expects the next
cycle to start with red right after `RGB`, so the pin check failed. No static check can know what a
sketch will do with its pins over time; only the run shows it. In D the same task passed on the first
attempt, which is also a reminder that the model is not deterministic at temperature 0.

**D passed everything in run 1 (25 of 25 on pass@3, 23 on pass@1).** Its two retries were the same T04 and T13 slips as in C, fixed on the second attempt. No D attempt failed in simulation this run, so the one thing D adds over C (retrying on what the simulator saw) was not exercised; in C the two simulation failures (T05, T18) had no retry to use. One run is not enough to put a number on that gap.

**One C failure is the checker's, not the model's (T18).** The redone C design put the LED's anode on 3V3 and its cathode through the resistor to D2, and drove D2 low to turn it on. That LED lights on a desk. The scenario expects D2 high while HEATING, so the harness marked it a fail, and the table reports what the harness said. Since 16 Nov 2026 the LED scenarios say "led1 on" (`expect-part`) and the harness derives the pin level from the wiring, so this design would pass; the run 1 numbers are left as the harness scored them at the time.

## Why attempts failed

The failure table above counts every failed attempt in the run folders by the first thing the
feedback names. For run 1 the whole story is short:

| Category | Where it showed up | Caught by |
|---|---|---|
| invented part type | A, 13 tasks | schema |
| invented pin name | A, 11 tasks | lint |
| missing library | A T04 (`NewPing.h`) | compile |
| 5 V part on the 3.3 V rail | C T04, D T04 | electrical |
| removed library call (`ledcSetup`) | C T13, D T13 | compile |
| escaped quote in a string | C T12 | compile |
| behaviour the prompt did not ask for | C T05 | simulation only |
| four times the requested motion, status line after the timeout | B T25 | simulation only |
| LED wired active-low, pin check assumed active-high | C T18 | simulation only (checker assumption) |
| 5 V part on the 3.3 V rail | B T04, B T14 | electrical |
| stopped after the status line, pins left low | B T01, B T05 | simulation only |
| wrong status line text (`RGB=RED`) | B T05 | simulation only |

No run 1 attempt failed the consistency rung (a GPIO number in the firmware that is not wired). The
prompt states the GPIO for every task, which is probably why; the rung exists for free-form prompts in
the web app.

## Caveats, read these before quoting the table

- A and B get one attempt and C and D get three. pass@3 is not a like-for-like comparison across the four. Read pass@1 for the effect of the catalogue and of feedback on the *first* design (B, C and D send the same first prompt, so their pass@1 should match, and the spread between them is sampling noise). Read pass@3 for what feedback buys given the extra tries.
- One run so far. Twenty-five tasks make each task worth four percentage points. Runs 2 and 3 will turn the single numbers into ranges.
- Temperature 0 on a hosted model is not deterministic (T05 above).
- Five rows of run 1 were first written as failures for reasons that had nothing to do with the model: T10 and T18 in C and T18 and T19 in D hit Groq's daily token cap, and T25 in B was a simulator flake (two runs with an empty serial log; the same binary passed by hand). The sweep's wait for the window was capped at 30 minutes and Groq asked for longer. Those five tasks were run again with `--only ... --merge`, which records the redo inside the results file (`redone`). The bench command now retries such tasks on its own and the cap is two hours.
- Every task is a single ESP32 DevKit v1 with parts from the catalogue, and the prompt fixes the GPIO numbers so the scenario can check the pins. Nothing here says anything about open-ended designs.
- Groq's free tier is 200K tokens a rolling day. C and D each use about 100K for 25 tasks, so one full sweep of all four versions takes two to three days of waiting. The wall-clock seconds in the JSON include those waits and mean nothing.
- The five-task pilot from October is kept under `pilot_5_tasks/` for the record. Its numbers (A 1/5, B 3/5, C 3/5, D 5/5) were on a different catalogue snapshot and before the pin checks, and are not comparable with this table.
- A first A and B sweep on 14 Nov (A 0/25, B 15/25) was run before two harness fixes that normalise model slips (double-escaped firmware, upper-case ids). It is kept under `run0_before_normalisation/` and not reported.

## Reproducing

```
set -a; . ./.env; set +a          # WOKWI_CLI_TOKEN and GROQ_API_KEY
for c in A B C D; do circuitmind bench $c --provider groq --label run2 --yes; done
circuitmind report --runs runs/bench/<stamp of each sweep>
```

Each sweep prints its simulated-minute cost and the request count before spending anything (drop
`--yes` to be asked), writes `benchmark/results/<config>_<label>.json` with per-task rows, and keeps
every attempt's prompt, reply, design, firmware and feedback under `runs/bench/<stamp>/`. The
`report` command prints the tables in this file from the results files, as min to max across runs.
