# Demo runs, 18 October 2026

Real runs of `circuitmind generate` with Gemini (gemini-flash-latest) on the free tier, temperature 0, catalogue snapshot 85454b7f. Simulation rung not run (no token yet); the four free rungs are shown.

## Run 1: servo plus button, three attempts

Request: *A servo that sweeps from 0 to 180 degrees and back when a pushbutton is pressed. Print SWEEP to serial after one full sweep.*

### Attempt 1: invented a pin name

```
[schema] passed
[lint] FAILED: 1 error(s), 0 warning(s)
invalid-pin: Invalid pin "VPlus" for part "servo1" (type: wokwi-servo). Valid pins: GND, V+, PWM (servo1)
```

### Attempt 2: used a library that was not installed

```
[schema] passed
[lint] passed
[compile] FAILED: compilation failed
sketch.ino:1:10: fatal error: ESP32Servo.h: No such file or directory
Error during build: exit status 1
```

### Attempt 3: passed

```
[schema] passed
[lint] passed
[compile] passed
[consistency] passed
```

Final wiring:

- `servo1:GND` to `esp:GND.1`
- `servo1:V+` to `esp:VIN`
- `servo1:PWM` to `esp:D18`
- `btn1:1.l` to `esp:D4`
- `btn1:2.l` to `esp:GND.2`

What happened: lint caught a pin the model made up (`VPlus`) and listed the real ones. The model fixed it and reached for `ESP32Servo`, which was not installed at the time, so compile failed. On the third attempt it wrote the servo pulse timing by hand and passed every free check. Nothing here was scripted; every correction came from the feedback the ladder produced. `ESP32Servo` is now part of the toolchain.

## Run 2: blink, one attempt

Request: task T01 prompt. Passed schema, lint, compile and consistency on the first attempt. 1889 tokens in, 342 out, 8.6 s model latency, 13 s compile.

## Run 3: RGB cycle, one attempt

Request: task T05 prompt. Passed all four free rungs on the first attempt. Three resistors, seven connections, correct common-cathode wiring. 1891 tokens in, 876 out.

## What this shows

- The model can produce a valid design in the exact format the checker expects. This was the main open risk in the design document and it is now closed.
- The retry loop works on real failures, not just scripted ones.
- Compile is the slow rung at about 13 s cold per attempt; everything else is under half a second.

## Later the same day: simulation rung, quotas, and the first benchmark

- First full-ladder pass with a real Wokwi token: T01 reference, simulate rung 5.5 s wall including upload. No `$serialMonitor` wiring needed on the ESP32 DevKit v1; serial is captured without it.
- `wait-serial` ends the run as soon as the text matches: a run with a 30 s timeout finished in 4.1 s wall. Budget is charged for simulated time used, not the ceiling.
- All five task references pass the full ladder including simulation.
- The T02 scenario had the check after the button release; the model's design printed PRESSED and the scenario still missed it. The reference did too. Scenario fixed to listen before the press. A task is only as good as its scenario.
- Gemini free tier: 20 requests per day on `gemini-flash-latest`. Enough for a demo, not for a four-configuration sweep. The sweep moved to Groq (`openai/gpt-oss-120b`), where the model also answers in about 3 s instead of 8 to 30.
- Full results in `benchmark/results/README.md`.
