# Decisions and lessons

Why things are the way they are. Read this before changing anything that looks odd.
Newest at the bottom.

## Architecture

**The model writes a small design (IR), never diagram.json.**
diagram.json carries x/y positions, wire colours and serial-monitor wiring. None of that
affects correctness and models get it wrong constantly. The model fills in parts,
connections, firmware and a status line; `expand.py` generates the rest. Smaller surface
for mistakes, and layout bugs can't exist.

**Checks run cheapest first and stop at the first failure.**
Schema, lint, compile and consistency are free and local. Simulation costs minutes from
a 50-minute monthly budget. Nothing reaches the simulator that could have been rejected
for free.

**The simulation verdict is the exit code, never the serial log.**
wokwi-cli exits 0 when the scenario's wait-serial matches, 42 on timeout (we set that
with --timeout-exit-code), anything else on error. The log can be truncated or
interleaved; the exit code cannot.

**Exit 42 is retried once, nothing else is.**
The simulator occasionally stalls on its first run. A second 42 is a real failure.
A hang (wokwi-cli never returning) is not retried, because it would cost another two
minutes of wall time for nothing.

**Every attempt is written to disk.**
reply.json, ir.json, diagram.json, sketch.ino, feedback.txt, serial.log, summary.json
under runs/. Any run can be inspected after the fact. This is how most bugs below were found.

**Tests never call a model or the simulator.**
`MockProvider` plays scripted replies. CI runs ruff and pytest only. Simulation budget
is spent only by a person running a command on purpose.

**Engine runs on a laptop, not a server.**
arduino-cli, the ESP32 core and wokwi-cli need to be installed somewhere; hosting that
costs money and the project has a zero-spend rule. The web app is static and talks to
http://127.0.0.1:8000. Chrome is required because other browsers block a page served
over HTTPS from calling localhost.

## Providers

**Groq (openai/gpt-oss-120b) is the default, not Gemini.**
Gemini's free tier on gemini-flash-latest allows 20 requests a day, which is less than
one benchmark configuration. Groq allows about 1000. Gemini stays supported for a
second-model comparison, run over several days.

**The User-Agent header on Groq requests is required.**
Without it Cloudflare returns HTTP 403 error 1010. Do not remove
`User-Agent: circuitmind/0.1` from providers.py.

**Requests are paced (Pacer) and retried on 429/5xx/network errors with backoff.**
Free tiers rate-limit by the minute. A daily-quota exhaustion is detected and reported
instead of retried forever.

**`static` is stripped from setup() and loop() before compiling.**
gpt-oss-120b regularly writes `static void setup()`. Arduino's build declares those two
functions for the core to call, so `static` makes the link fail. Stripping it never
changes a correct sketch. The prompt also says not to do it; the strip is the safety net.

**The status-line rule says "fixed prefix", not an example value.**
An early prompt showed `DIST=42` as an example and the model printed the literal string
`DIST=42`. The prompt now says to print the prefix and then the value.

## Benchmark

**Scenarios press buttons before waiting, and wait right after the press.**
T02 originally listened for PRESSED after the release step, and missed it. wait-serial
only sees output produced after the step starts.

**Reference designs must pass the full ladder, including simulation, before a task is
committed.** A task whose reference does not pass is a broken ruler. Every task PR
includes the PASS lines.

**T09 (I2C LCD) probes the bus before calling lcd.init().**
The first version hung the simulator with an empty serial log. With Wire.setTimeOut(50)
and a beginTransmission/endTransmission probe at 0x27, it passes and a wiring mistake
fails fast with NO_LCD instead of hanging.

**T14 distance threshold is 30 cm, not 100.**
The HC-SR04's default distance in the simulator must read as FAR on the first sample
without depending on the exact default value.

**Bench runs each task inside try/except and records failed_rung="error".**
One crashing task used to take the whole sweep down with it.

**T23 and T24 use a joystick and an MPU6050, not a keypad and a rotary encoder.**
The plan said keypad and KY-040. Wokwi scenarios can only drive parts that have
automation controls (pushbutton, potentiometer, joystick, MPU6050, photoresistor, HX711
and a few sensors). The keypad and KY-040 have none: a set-control step on them is
accepted and silently does nothing, and the sketch sits at its boot line until the
timeout. A task whose scenario cannot exercise the input only proves the sketch boots,
so both were replaced with parts the scenario can move (joystick y, MPU6050 accelX).

**The compile rung retries once when arduino-cli loses a file in its own build folder.**
Seen on a handful of `circuitmind reference` runs (3 of 20 in one sweep, and about one
in three while probing one task) when the same workdir is deleted and rebuilt: "opening dependency file .../build/sketch/sketch.ino.cpp.d: No such file or
directory" or ".../sketch.ino.cpp.merged: no such file or directory", failing after 8 to
10 s. The sketch is never at fault and the next run passes. Ruled out: parallel runs (it
happens alone), cloud sync on the folder, leftover arduino-cli processes, and arduino-cli
itself (the same delete-and-rebuild loop by hand passed 7 times out of 7). The cause is
still unknown. The retry fires only when the missing file is inside the build folder,
wipes that folder, builds again, and says so in the rung summary ("second try"). A missing
header or any other error is reported straight away as before.

**Reference checks run one at a time, never in parallel.**
Two `circuitmind reference` runs started together made arduino-cli create a `build 2`
directory and fail with "opening dependency file ... No such file or directory". The
design was fine; the compile just raced. Run them in sequence.

**T25 drives the stepper coils straight from four GPIOs.**
The catalogue has no driver board. The simulator accepts it and the Stepper library
sequence is what a real driver would see, so coil pairing and the library call are still
tested. The guide should say a real build needs an H-bridge between the ESP32 and the
motor. The Stepper library is now part of the toolchain.

**Scenarios assert pin levels with `expect-pin`, and the prompt names those GPIOs.**
A status line only proves the sketch printed something. `expect-pin` (part-id `esp`,
name `D13`, value 0 or 1) checks the real pin level at that moment. A wrong value fails the
run with "simulation failed (exit 1)", confirmed with a deliberate wrong check before any
scenario relied on it. The board pin must be written `D2`, not `2`. Because bench runs
model designs against the same fixed scenario, a pin check only works if the prompt fixes
the GPIO ("red LED on GPIO 2"), so the seven prompts with pin checks now do. Prompts that
leave the pin free (sensors, servos, buttons) keep their status-line check only.

**Where a pin check is not possible, the scenario says nothing extra.**
PWM outputs (LED fade, servo signal) are pulse trains; an instantaneous level check would
be luck. The stepper coil pattern after a move is a library detail, not the requested
result. LCD text cannot be read: wokwi-cli has no `expect-text`, only `take-screenshot`
image comparison, which is brittle and tied to one rendering. Those tasks (T03, T09, T13,
T15, T22, T23, T25) keep status-line checks only, and their notes say why.

**Scenario part ids and prompts are a known weak spot.**
set-control steps name the part (`btn1`, `joy1`, `imu1`). The prompts do not; the model
uses those ids only because the system prompt gives them as examples. A model design that
calls its button `button1` would fail at simulate for no electrical reason. Not fixed yet;
the roadmap carries it.

**Results report pass@1 and pass@3, never a single pass count.**
A and B get one attempt, C and D get three. One "passed" column lets D look better partly
because it had more tries. pass@1 (first design passed every check) is the like-for-like
number across all four; pass@3 (any allowed attempt passed) shows what feedback buys. The
loop records which attempt passed (`passed_attempt`), bench writes both counts, and the
summary table derives pass@1 from attempt counts for result files written before the key
existed. The pilot's pass@1 (A 1, B 3, C 2, D 3) was recovered that way.

**The electrical rung is wiring rules only, with rough datasheet numbers.**
It builds the nets from the connections and checks five things the simulator does not:
rails shorted together, an LED with no resistor on either side (resistors are crossed when
following a GPIO to a part), servo V+ and HC-SR04 VCC on VIN rather than 3V3, a driven
part reached from D34/D35/VN/VP, and a current total over 500 mA (one USB 2.0 port). The
per-part draws are ballpark typical figures from datasheets (SG90 about 250 mA moving,
28BYJ-48 about 240 mA, HC-SR04 15 mA, DHT22 under 2 mA, MPU6050 under 4 mA) plus 80 mA
for the board without WiFi. They are for catching a design that cannot run from USB, not
for measuring anything; the simulator does not model current at all. Every reference
design passes the rung, and that is a test.

**Five tasks was a pilot; the numbers A 1/5, B 3/5, C 3/5, D 5/5 are from one run.**
Temperature 0 is still not deterministic across runs. The plan is 25 tasks and three
repeats so results are reported as a range.

## Web app

**Free-form prompts get a scenario built from the design itself.**
Benchmark tasks have hand-written scenarios; a user's prompt does not. The API presses
every pushbutton in the design, then waits for the status line the model declared.

**The guide says plainly when a design did not pass.**
`build_guide(..., verified=False)` adds a note that the design failed verification and
should not be built as is. A design that failed is shown so the user can see what was
tried, never presented as working.

## Things that were claimed and had to be corrected

**EmbedBench figures.** An early draft overstated what the EmbedBench paper showed. The
correct figures from its abstract are task-specific (ESP-IDF) and should be quoted
exactly or not at all. Rule since then: no number goes into a doc without a source
next to it.
