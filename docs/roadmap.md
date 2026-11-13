# Roadmap

One ordered list. Work top to bottom. Do not start a later section while an earlier one has open items, unless an item is blocked and says so. Tick items as PRs merge.

## Done
- Validation ladder: schema, lint, compile, consistency, electrical, simulate. A stalled simulator is a failed rung, not a crash.
- Providers: Groq (default), Gemini, OpenRouter, mock for tests. Paced, retried, quota-aware.
- Generation loop with feedback retry (max 3); every attempt saved to disk.
- Build guide: wiring steps, parts and prices, notes, honest "unverified" label.
- Web workspace (static pages on Vercel + local FastAPI engine with live progress).
- Benchmark runner for configurations A to D; pilot on 5 tasks: A 1/5, B 3/5, C 3/5, D 5/5.
- Benchmark suite at 20 tasks (T01 to T15, T21 to T25), every reference passes all five rungs.
- README with HLD, LLD and simulation-flow diagrams; docs/decisions.md for the why.

## 0. Fix what is weak before building on it
These are known holes in what exists. Nothing new gets built until they are closed.

- [x] **Scenarios check pins, not just text.** Today a design passes if the firmware prints the status line. Add `expect-pin` steps to every scenario where the result is a pin state (LED on, buzzer high, relay on) and `expect-text` where an LCD shows something. Keep the status line as the "done" marker. Re-run every reference; any that fails now was passing for the wrong reason. Done for pins; `expect-text` does not exist in wokwi-cli (only image screenshots), so LCD tasks keep the status-line check.
- [ ] **Scenario part ids come from the prompt.** set-control names parts (btn1, joy1, imu1) that the prompt never states; the model matches them only because the system prompt uses them as examples. Either the prompt states the ids or the harness maps scenario parts to design parts by type.
- [x] **Honest scoring.** The loop records which attempt passed. Bench reports pass@1 (first attempt passed) and pass@3 (any attempt passed) for every configuration. The README table shows both columns. A gets one attempt, D gets three; comparing them on pass@3 alone is not fair and the write-up must say so.
- [x] **Electrical rule check as a new rung ("electrical", between consistency and simulate).** Pure Python, no budget: power rails never wired to each other; every LED path has a resistor; servo and HC-SR04 V+ on VIN not 3V3; no output driven on D34/D35/VN/VP; a rough current sum against the USB limit using a per-part table. Each failure produces plain feedback the model can act on. Tests for each rule.
- [x] **Consistency check: fewer pass-throughs.** Resolve pins passed through helper functions with constant arguments and simple arrays. Count how many references still pass through; report it. Before: 1 of 20 (T10, a `pressed(int pin)` helper). After: 0 of 20. Five references (T03, T08, T09, T22, T25) resolve with nothing to check because their pins live in library constructors (DHT, LiquidCrystal, Stepper, Wire); `servo.attach(pin)` is now seen.
- [x] **Free-form scenarios say what they checked.** The web app's auto-built scenario (press every button, wait for status line) is weaker than a hand-written one. The result screen shows exactly what was exercised ("pressed btn1, waited for PRESSED") so "verified" is never overstated. Add `expect-pin` for any LED wired in the design when the prompt says it should turn on.
- [x] **Failure screen.** When all attempts fail, the web app shows one plain sentence per attempt (which rung, why), a suggestion ("try naming the exact parts", "this needs a part the simulator does not have"), and a "try an example" button with four prompts known to pass. No raw rung dumps.
- [ ] **Out-of-scope prompts.** A request that needs parts outside the catalogue (drone, mains power, walking robot) gets a clear answer before any model call where possible (keyword screen) and a model-side rule: if the request cannot be built from the catalogue, return the closest buildable sub-project and say what was left out. Test with five out-of-scope prompts.

## 1. Finish the task suite (25)
- [ ] T16 to T20: slide switch, LDR, PIR, 7-segment, relay. All five rungs must pass. If a part has no scenario control, pick another part; never ship a task the simulator cannot check.
- [x] T21 to T25: two sensors, sensor + LCD, joystick + servo, MPU6050 tilt alarm, stepper. Keypad and rotary encoder dropped: no scenario control exists for them.
- [ ] Every scenario in the suite uses `expect-pin` or `expect-text` where applicable (from section 0).

## 2. Website works for anyone (free stack)
The frontend is already deployed on Vercel. The gap is the engine, which runs only on the owner's laptop.

- [ ] Host the engine on a Hugging Face Space (Docker, free CPU tier: 2 vCPU, 16 GB RAM). Existing Dockerfile, port 7860, WOKWI_CLI_TOKEN and GROQ_API_KEY as Space secrets, warm build cache baked into the image. `/health` reachable from the internet.
- [ ] web/app.html defaults to the Space URL (localhost stays as a developer override). Handle a sleeping Space: show "engine waking up, about a minute" and retry, never a dead page.
- [ ] Access control before the URL is shared: Supabase Auth (email link and Google) in the static pages; engine verifies the Supabase token on POST /generate; per-user cap of 5 runs a day; engine refuses with a plain message when the monthly simulation budget is nearly gone.
- [ ] Saved designs: Supabase table (user, prompt, design JSON, guide, diagram.json, status, time). "My designs" page lists them and reopens the guide.
- [ ] Workspace polish: example prompts on the empty screen, "attempt N of 3", each rung lights up as it passes, estimated wait shown, budget-used-this-month shown.
- [ ] Landing page: real "Open workspace" and "Sign in" buttons, a three-step "how it works" strip using the diagrams, the honest scope sentence (what it builds, what it refuses).
- [ ] Speed: compile starts the moment the model replies; warm cache on the Space; target under 45 s for a first-attempt pass. Measured and written down, not guessed.
- [ ] Test as a stranger: fresh browser, three prompts (one easy, one medium, one out of scope). Fix whatever breaks. Repeat until clean twice in a row.

## 3. Benchmark runs
- Budget first: 50 simulated minutes a month on the free tier. Check https://wokwi.com/dashboard/ci before each sweep. The 5-task pilot used about 75 simulated seconds for all four configs; 25 tasks is roughly 6 to 7 minutes per full sweep.
- [ ] Add `--yes` and a printed cost estimate to `circuitmind bench`; it asks before spending.
- [ ] Run A, B, C, D once on all 25 with Groq. Save as results/<config>_run1.json.
- [ ] Repeat twice more on different days (run2, run3). Results are reported as min to max across runs.
- [ ] One sweep of D with Gemini if budget allows (20 requests a day on the free tier, so it takes days).

## 4. Results write-up
- [ ] benchmark/results/README.md: table with pass@1 and pass@3 per config, min to max over three runs; per-task matrix (which tasks fail where, at which rung); failure categories (invented pin, wrong GPIO, missing resistor, electrical rule, library error, logic error caught only by simulation); what feedback fixed and what it did not.
- [ ] README status table updated to the 25-task numbers. Plain-language reading of the result, same style as "Does the checking actually help?".
- [ ] One page for the project review: problem, approach, the table, the honest limits.

## 5. Towards an electronics engine of our own
Only after sections 0 to 4 are closed.
- [ ] ngspice rung ("analog"): convert a design to a SPICE netlist using a per-part model table (LED as diode with forward voltage, resistor, servo and sensors as current draws, ESP32 pin as 3.3 V source with a current limit), run ngspice, read currents and voltages, fail on over-current or under-voltage with plain feedback. Starts with LEDs and resistors only; grows part by part.
- [ ] Measure: how many model designs that pass Wokwi fail the analog rung. That number is the argument for the rung.

## Not in scope this semester
- Physics simulation (drones, anything that flies or drives). The route exists (PX4 + Gazebo) and is a separate project.
- Boards other than ESP32 DevKit v1.
- Paid hosting or paid APIs of any kind.
