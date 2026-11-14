# Background: the thinking behind the project

Plain-language notes on why the project is shaped the way it is, what else exists, and
where it could go. For anyone who wants to understand the choices, including future us.

## The problem, in one paragraph
Ask any chatbot for an ESP32 circuit and you get a wiring list and code that look right.
Some of the time they are. The rest of the time a pin name is invented, the code drives
GPIO 5 while the wire is on GPIO 4, a library call is from an old version, or it compiles
and does nothing. A beginner cannot tell which case they are in until they have bought
parts and spent an evening. The fix is not a smarter model. It is never showing a design
that has not been run.

## Why the checks are ordered the way they are
Schema, lint, compile and consistency are free and take seconds. Simulation costs minutes
from a monthly budget and takes 10 to 30 seconds. So the cheap checks go first and the
run stops at the first failure. Most model mistakes (bad pin names, wrong GPIO numbers,
compile errors) die in the free rungs. Only designs that look right reach the simulator,
which is the one check that can catch "compiles but does nothing".

## What "verified" means, and what it does not
Verified means: the firmware compiled for a real ESP32 and, in a simulator that emulates
the chip and the parts, the scenario's inputs were applied and the expected result was
seen. It does not mean a part will not overheat (no current simulation), that the real
part batch behaves like the simulated one, or that the design is the best design.

Weakness found on 13 Nov: for a long time the "expected result" was only the status line
printed to serial. A sketch that prints BLINK without touching the LED would have passed.
The fix is `expect-pin` steps in scenarios (assert the GPIO is high or low at that moment)
and `expect-text` for LCDs. See roadmap section 0.

## Why the model writes a small design and not the simulator's own file
Wokwi's diagram.json carries x/y positions, wire colours and serial-monitor wiring. None
of that affects whether the circuit works, and models get it wrong constantly. The model
fills in the parts, the connections, the firmware and a status line; `expand.py` does the
rest. Smaller surface for mistakes.

## Why the four configurations
A (bare model) is the baseline, what you get from a chatbot. B adds the parts catalogue
to the prompt: does telling the model the real parts and pins help? C adds retry on the
free checks: does feeding back compile errors help? D adds retry on simulation: does
feeding back what actually happened when it ran help? Each step isolates one idea.

Fairness note: A gets one attempt, D gets up to three. Report pass@1 (first attempt
passed) for all four as well as pass@3, or the comparison flatters D.

## Scope: what it builds and what it refuses
Builds: anything made from an ESP32 DevKit v1 and the parts the simulator knows. Lights,
buttons, buzzers, potentiometers, servos, a small stepper, distance and temperature
sensors, motion and light sensors, an IMU, a joystick, small displays, a relay. That is
most of what a beginner or a second-year student actually builds.

Refuses: anything the simulator cannot run. A drone (brushless motors, ESCs, battery
physics, flight control, lift), mains power, high-current motor drivers, walking robots.
The right answer to "build me a drone" is not a guess; it is "I cannot verify a drone;
here is the part I can build and prove: the ESP32 reading an MPU6050 tilt sensor, which
is the first thing inside every flight controller." A clear no is the product's edge over
a chatbot's confident yes.

## Other simulators, and why none of them alone is enough
- Wokwi: ESP32, Arduino, Pico, ~30 parts, scriptable cloud CLI, free tier. The only one
  with a free, automatable API. What we use.
- SimulIDE: open source, desktop, AVR/PIC/Uno-class chips. No ESP32, no real scripting.
- Proteus: industry standard, MCU plus analog. Paid, Windows, not automatable for free.
- Tinkercad Circuits: browser, Uno only, no API.
- QEMU (Espressif fork): emulates the ESP32 CPU. No parts.
- Renode: open source, headless, many chips, peripheral models not breadboard parts.
  Serious firmware-CI tool, steep learning curve.
- ngspice: free, open source, command line analog simulation. Voltages, currents, what
  burns. No microcontroller. The natural second rung.
- Falstad CircuitJS: browser, open source, great for teaching, no automation.
- Gazebo, Webots, PyBullet, PX4 SITL: open-source physics for things that fly or drive.
  They simulate the vehicle, not the wiring.

Four separate worlds, no bridge. The gap is not a better simulator; it is the layer that
drives several from one plain-English request. The harness is already that layer with
one simulator plugged in.

## Towards an engine of our own, in stages
1. Rule-based electrical checks (weeks, free): rails never shorted, LEDs through
   resistors, servo on 5 V, nothing driven on input-only pins, rough current sum against
   the USB limit. Catches the mistakes that fry parts. Roadmap section 0.
2. ngspice rung (months): design to SPICE netlist with a per-part model table; read
   currents and voltages back. "Verified" grows to include "will not burn". Roadmap
   section 5.
3. Own MCU emulation (a year plus): only if Wokwi becomes a blocker.
4. Physics (years): PX4 plus Gazebo for anything that flies. A separate project.

## Why a run takes about a minute, and what can be cut
Model reply 5 to 10 s on Groq. Compile 3 s warm, 30 to 40 s cold. Simulation 5 to 30 s
because the scenario has to wait for the behaviour (a blink is a blink). A retry doubles
it. What can be cut: keep the build cache warm on the hosted engine (saves the cold
compile), start compiling the moment the model replies, show each rung lighting up so
the wait is watchable. Realistic target for a first-attempt pass: under 45 s. Under 10 s
is not possible with a real compiler and a real simulator, and faking it is the one
thing this product must never do.

## Why everything is free
Zero-spend rule from day one. Groq and Gemini free tiers for the model, Wokwi free tier
(50 simulated minutes a month) for simulation, Vercel Hobby for the static site, a
Hugging Face Space free CPU tier for hosting the engine, Supabase free tier for sign-in
and saved designs. The budget constraint shaped the architecture: it is why cheap checks
run first and why the benchmark is small and repeated rather than huge.

## Related work (from the PRD)
- Flux.ai: AI-assisted PCB design with a copilot. Designs boards; does not run firmware
  against the circuit in a simulator with feedback.
- EmbedBench (paper): benchmark of LLMs writing embedded firmware; figures are
  task-specific (ESP-IDF) and should be quoted exactly from the abstract or not at all.
- General chatbots: produce circuit plus code with no verification.
Nothing free closes the loop from plain-English request to simulated, verified design
with a build guide. That gap is the project.
