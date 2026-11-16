# CircuitMind in one page

Project review summary. Piyush Thakkar, B.Tech CS (AI/ML), Polaris School of Technology. OJT project, semester ending December 2026.

## The problem

Ask a chatbot for a small electronics project ("an ESP32 that blinks an LED when I press a button") and you get a parts list, wiring and Arduino code that look right. Often they are not: a pin name is invented, the code drives a GPIO that nothing is wired to, a library call is from an old version, or it compiles and does nothing. A beginner cannot tell which case they are in until the parts are bought and an evening is gone.

## The approach

Never show a design that has not been watched running. A language model writes a small design (parts, pin-to-pin connections, firmware, and a status line the firmware prints when done). The design then climbs a ladder of checks, cheapest first, and stops at the first failure:

1. **Schema**: every part type and pin name exists in a catalogue extracted from the simulator itself.
2. **Lint**: the simulator's own wiring checker.
3. **Compile**: built for a real ESP32 DevKit v1 with arduino-cli.
4. **Consistency**: GPIO numbers in the firmware match the pins that are wired.
5. **Electrical**: rails not shorted, every LED has a resistor, 5 V parts on VIN, nothing driven on input-only pins, rough current total under the USB limit.
6. **Simulate**: the firmware runs in the Wokwi simulator with the design's wiring; a scenario presses the buttons, moves the sensors and checks the pins and the status line.

A failure goes back to the model with the error text and the previous design, up to three attempts. Only a design that passed is shown, with a beginner's build guide (wiring steps, parts and prices, the code). The first five checks are free and take about 15 seconds; the simulation costs minutes from a free monthly budget, so nothing reaches it that could have been rejected for free.

Everything runs on free tiers: Groq for the model, Wokwi for simulation, Vercel for the pages, Supabase for sign-in and saved designs. The website is live at https://circuit-mind-landing.vercel.app; the engine runs on a laptop and is shared through a tunnel link.

## Does the checking help? The benchmark

Twenty-five tasks (LEDs, buttons, buzzers, servos, a stepper, distance and temperature sensors, LDR, joystick, MPU6050, LCD, 7-segment, relay), each with a scenario that checks pins, not just printed text. Four versions of the system, same model, run 1 on 15 and 16 Nov 2026:

| Version | What it has | pass@1 (of 25) | pass@3 (of 25) |
|---|---|---|---|
| A | bare model | 0 | 0 |
| B | + parts catalogue in the prompt | 20 | 20 |
| C | + retry on schema, lint, compile, consistency, electrical errors | 20 | 23 |
| D | + retry on simulation errors too | 23 | 25 |

pass@1: the first design passed every check including the simulation. pass@3: some attempt passed within the attempts the version allows (one for A and B, three for C and D), so A against D on pass@3 is one shot against three and the write-up says so.

What it shows:

- The bare model produced zero designs the simulator would load: it invents part types and pin names (A).
- Telling it the real parts and pins is the biggest single step (B).
- Feeding compile and electrical errors back fixes exactly the mistakes those checks catch: a 5 V sensor wired to 3.3 V, a library call removed in the current ESP32 core, a stray escaped quote (C).
- The one thing the free checks cannot see is what the sketch does over time. In run 1 a design cycled an RGB LED correctly and then switched it off for a second nobody asked for; only the simulation caught that, and only D can retry on it (D).

Full tables, per-task matrix, failure categories and caveats: `benchmark/results/README.md`.

## The honest limits

- One run so far; runs 2 and 3 on other days are planned so the numbers become ranges. Each task is four percentage points.
- "Verified in simulation" means the logic and wiring behaved in Wokwi. It says nothing about current draw, heat, or the real part batch. The build guide says so. An analog rung (ngspice) is the next step and is not built.
- One board (ESP32 DevKit v1), about 30 parts, single-board projects. Drones, mains power and motors above the USB limit are refused on purpose.
- The engine runs on a laptop. Free hosts that can run the ESP32 toolchain want a card on file, which the zero-spend rule does not allow, so the live workspace is up while the laptop is.
- The model is not deterministic at temperature 0; some of the gap between versions is sampling noise, which repeated runs are for.
