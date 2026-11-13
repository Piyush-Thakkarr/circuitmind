# Roadmap

What is done, what is left, in order. Tick items off as PRs merge.

## Done
- Validation ladder: schema, lint, compile, consistency, simulate. Stalled simulator is a failed rung, not a crash.
- Model providers: Groq (default), Gemini, OpenRouter, mock for tests.
- Generation loop with feedback retry (max 3), every attempt saved to disk.
- Build guide: wiring steps, parts and prices, notes, honest "unverified" label.
- Web workspace (static page + local FastAPI engine with live progress).
- Benchmark runner for configurations A to D.
- Pilot results on 5 tasks: A 1/5, B 3/5, C 3/5, D 5/5.
- Benchmark suite at 20 tasks (T01 to T15, T21 to T25), every reference passes the full ladder.
- README with HLD, LLD and simulation-flow diagrams.

## 1. Finish the task suite (target 25)
- [ ] T16 to T20: parts not yet used (slide switch, LDR, PIR, 7-segment, relay).
- [x] T21 to T25: harder combinations (two sensors, sensor + LCD, joystick + servo, MPU6050 tilt alarm, stepper). Keypad and rotary encoder were dropped: the simulator has no scenario control to press a key or turn the knob, so a task with them could never be checked.
- Each task: task.yaml, scenario.yaml, reference/ir.json; reference must print `outcome: PASS` from `circuitmind reference <id>`.
- Keep categories balanced: output_basics, inputs, sensors, actuators, displays.

## 2. Benchmark runs
- Budget first: Wokwi free tier is 50 simulated minutes a month. The 5-task, 4-config pilot used about 75 simulated seconds. 25 tasks x 4 configs is roughly 6 to 7 minutes per full sweep; three repeats is about 20 minutes. Check remaining budget at https://wokwi.com/dashboard/ci before each sweep.
- [ ] Run A, B, C, D once on all 25 tasks with Groq (`circuitmind bench A --provider groq`, then B, C, D).
- [ ] Repeat the sweep two more times on different days (temperature 0 is still not deterministic; three runs give a range, not a single lucky number).
- [ ] Keep every results JSON; name repeats so they do not overwrite (results/<config>_run<n>.json).
- [ ] If budget allows, one sweep of D with Gemini for a second model (20 requests/day on the free tier, so it takes several days).

## 3. Results write-up (benchmark/results/README.md)
- [ ] Table: config x pass count, with min/max across the three runs.
- [ ] Per-task matrix: which tasks fail in which config, and at which rung.
- [ ] Failure categories: invented pin name, wrong GPIO number, missing resistor, library/version error, logic error only caught in simulation.
- [ ] What feedback fixed and what it did not (tasks that failed all 3 attempts in D, and why).
- [ ] Plain-language reading of the numbers, same style as the README "Does the checking actually help?" section.
- [ ] Update the README status table with the 25-task numbers.

## 4. Small fixes
- [ ] Engine refuses a job politely when WOKWI_CLI_TOKEN is missing or budget is known to be exhausted, instead of failing at rung 5.
- [ ] Web app shows which attempt (1 of 3, 2 of 3) is running.
- [ ] `circuitmind bench` prints a budget estimate (tasks x timeout) before it starts and asks for confirmation.
- [ ] Re-test the Gemini provider end to end (last tested in October).

## 5. Final presentation material
- [ ] One-page summary for the project review: problem, approach, the table, what was learned.
- [ ] A 2-minute demo path: open the web app, run one prompt, show the attempt fail and retry, show the guide.
- [ ] Known limits, stated plainly: logic and wiring only (no current or power simulation), ESP32 DevKit v1 only, engine runs on a laptop.

## Not in scope for this phase
- Physics or electrical simulation beyond what Wokwi does.
- Hosting the engine on a server.
- Boards other than ESP32 DevKit v1.
