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
