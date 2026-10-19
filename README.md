# CircuitMind

Describe a small electronics project in plain English. CircuitMind designs the circuit, writes the code for it, runs it in a simulator to prove it works, and then gives you a step-by-step guide to build it on your desk.

Live demo: https://circuit-mind-landing.vercel.app (the engine behind it runs on a laptop, so the workspace only works while that laptop is up; see [Running it yourself](#running-it-yourself)).

## The problem

Ask any chatbot for "an ESP32 that blinks an LED when I press a button" and you get a wiring list and some Arduino code. It looks right. Maybe a third of the time it actually is. The rest of the time a pin name is made up, the code uses GPIO 5 but the wire goes to GPIO 4, or it compiles fine and then just does nothing. A beginner cannot tell which case they are in until they have bought the parts and spent an evening on it.

## What CircuitMind does differently

It never shows you a design it has not watched run.

1. You type what you want. Example: "Blink an LED once a second and print BLINK after two cycles."
2. A language model writes a small design: which parts, which pin connects to which, the firmware, and a short status line the firmware will print when the job is done (like `BLINK`).
3. The design goes through five checks, cheapest first:
   - **Schema**: are all the parts real, are the pin names real, is anything missing?
   - **Lint**: the simulator's own checker looks at the wiring.
   - **Compile**: the firmware is built for a real ESP32 with `arduino-cli`.
   - **Consistency**: the GPIO numbers in the code must match the pins that are actually wired.
   - **Simulate**: the compiled firmware and the wiring are run in the Wokwi simulator, which emulates the ESP32 and the parts. A small script presses any buttons and waits for the status line.
4. If any check fails, the exact error and the previous design go back to the model, and it tries again. Three tries, then it stops and tells you what went wrong.
5. If every check passes, you get a wiring guide written for a beginner, a parts list with rough prices, the firmware, and the exact circuit to open in Wokwi.

The first four checks are free and run on your machine in a few seconds. Only the last one costs anything (Wokwi's free tier gives 50 simulated minutes a month), and nothing reaches it that could have been rejected for free.

## Does the checking actually help?

That is the research question of the project. Five tasks were run through four versions of the system:

| Version | What it has | Passed (5 tasks) |
|---|---|---|
| A | bare model | 1 |
| B | + parts catalogue in the prompt | 3 |
| C | + retry on schema, lint, compile, consistency errors | 3 |
| D | + retry on simulation errors too | 5 |

Model: `openai/gpt-oss-120b` on Groq's free tier. Full table, per-task results and caveats in [`benchmark/results/README.md`](benchmark/results/README.md).

What the table says: without the catalogue, the model invents pin names (A). Telling it the real parts and pins fixes most of that (B). Retrying on compile errors alone did not add anything here, because the one wrong design in C passed every static check and only failed when it actually ran (C). Retrying on what the simulator saw caught it (D).

Five tasks is a pilot. The plan is 25 tasks and repeated runs.

## Architecture

Three diagrams. The first is the map, the second is the code, the third is what happens to one design.

### High-level design

![High-level design](docs/diagrams/hld.png)

This is what runs where. Read it left to right, the way a request travels.

- **Browser** (left). Two static pages hosted on Vercel. The landing page is the marketing page. The workspace app is where you type a project and watch the checks run. It has no logic of its own; it just talks to the engine.
- **Engine** (middle). A Python program that runs on the owner's laptop. The API server takes the request and streams progress back to the browser. The generation loop is the brain: it builds the prompt, calls the model, runs the ladder of checks, and retries. The validation ladder is the five checks. The build guide turns a passing design into instructions a person can follow. The benchmark runner drives the same loop in the four versions from the table above.
- **External** (right). Things we do not run ourselves, all on free tiers. The model provider (Groq, Gemini or OpenRouter, behind one interface). The Wokwi cloud simulator, which receives the compiled firmware and the wiring and runs them. The Wokwi part registry, which is where the parts catalogue comes from.

The arrow colours matter. Orange is the only model call. Red is a failed check going back into the loop for a retry. Teal is a verified design on its way to the user.

### Low-level design

![Low-level design](docs/diagrams/lld.png)

This is the actual code in `src/circuitmind`, one box per file, and who calls whom. Four columns:

- **Entry points.** `cli.py` is the command line. `api.py` is the web API. `bench.py` runs the benchmark. All three call the same `run_generation()` in `loop.py`; there is only one loop. `guide.py` turns a passing design into the human-readable guide.
- **The loop and what it needs.** `loop.py` owns the attempts. `prompt.py` holds the rules the model is given and builds the first prompt and the retry prompt. `providers.py` is the one place that talks to a model; Groq, Gemini and OpenRouter all look the same from the outside, and a `MockProvider` plays scripted replies so tests never need a key.
- **Data.** `ir.py` is the design itself, a small schema with parts, connections, firmware and the status line. The model fills this in and nothing else. `expand.py` turns a design into Wokwi's `diagram.json`, so the model never has to write that file. `catalogue.py` loads the list of allowed parts and their pins.
- **The ladder.** `harness/` has one file per check plus `ladder.py`, which runs them in order and stops at the first failure. Every check returns the same shape of result, and that result knows how to describe itself as text the model can act on.

The orange line over the top is the loop handing a design to the ladder. The red dashed line coming back around the bottom is the feedback from a failed check, plus the previous design, going into the retry prompt.

Four rules the code is built around, listed at the bottom of the diagram:

- The model never writes `diagram.json`. `expand()` does, so layout, wire colours and the serial wiring cannot be wrong.
- A design reaches the user only if the last check it ran passed. If it did not, the guide says so in plain words.
- Every attempt is saved to disk (the model's reply, the design, the diagram, the sketch, the feedback, the serial log), so any run can be inspected afterwards.
- Tests use the mock provider. CI never calls a model and never spends simulation time.

### Simulation flow

![Simulation flow](docs/diagrams/simulation-flow.png)

This follows one attempt from the model's reply to a verdict.

Down the left are the five checks in order. The model's JSON reply is parsed into a design; if that fails, it is a schema failure and no tool is run at all. Then lint, then compile, then consistency. Each of those is free and takes seconds. The teal "pass" arrows are the only way down; a failure at any step jumps straight to the red line at the bottom.

Only step 5 leaves the machine. It writes a `wokwi.toml` pointing at the compiled binary, picks a scenario file, and uploads the binary, the wiring and the scenario to Wokwi. A scenario is a tiny script: wait half a second, press any button the design has, then wait for the status line the firmware promised to print.

Inside Wokwi (the dashed box), a virtual ESP32 boots the binary, the parts in the diagram respond to it, and serial output streams back. The run ends in one of three ways, and the verdict is the exit code, never a guess from reading the log:

- the status line appeared: exit 0, **pass**. The design is marked verified and the guide is built.
- the timeout hit without the line: exit 42, **fail**. This is retried once, because the simulator occasionally stalls; a second 42 counts.
- anything else (a crash, a scenario error): **fail**.

On a fail, the feedback is the name of the check that failed, a one-line summary, and the last 20 lines of serial output. That text plus the previous design goes back to the model as attempt n+1, up to three.

The dashed "costs budget" marking matters: a full run of all five tasks through all four versions used about 75 simulated seconds out of the 50 free minutes a month.

## Repository layout

```
benchmark/tasks/     one folder per task: task.yaml, scenario.yaml, reference/
benchmark/results/   README.md with the table, plus one JSON per version
catalogue/parts.json part types and their valid pins, extracted from wokwi-cli lint
docs/                diagrams/ (the three images above), demo-runs.md (real transcripts)
src/circuitmind/     ir.py, expand.py, catalogue.py, prompt.py, providers.py,
                     loop.py, bench.py, guide.py, api.py, cli.py, harness/
tools/               extract_catalogue.py, setup_toolchain.sh
tests/               unit tests, no simulation, no network
web/                 index.html (landing page), app.html (workspace)
```

## Running it yourself

You need Python 3.11+, `arduino-cli` with the ESP32 core, and `wokwi-cli`. `tools/setup_toolchain.sh` installs all three.

```
pip install -e ".[dev]"
circuitmind tasks                                  # list the benchmark tasks
circuitmind reference T01_blink --no-simulate      # run the free checks on a known-good design, no model needed

export GROQ_API_KEY=gsk_...                        # free key from console.groq.com
circuitmind generate "blink an LED twice then print BLINK" --provider groq
circuitmind generate - --task T03_servo_sweep --provider groq   # use a benchmark task's prompt
# GEMINI_API_KEY with --provider gemini also works (free tier is 20 requests a day on the model tested)

export WOKWI_CLI_TOKEN=wok_...                     # from https://wokwi.com/dashboard/ci
circuitmind generate - --task T01_blink --simulate # all five checks, spends simulated seconds
```

Flags on `generate`: `--attempts N` (default 3), `--no-grounded` (leave the catalogue out of the prompt), `--no-feedback` (retry without sending the error back). Those two switches are what versions A to D are built from.

Run the benchmark:

```
circuitmind bench A --provider groq      # then B, C, D
```

### Web app

The pages in `web/` are static. They talk to a small API on your machine:

```
circuitmind serve                        # http://127.0.0.1:8000
```

Open `web/app.html` (or the deployed site's `/app.html`) in Chrome, type a project, and watch the checks run. The page streams progress from the API and shows the wiring guide, parts list and firmware when a design passes. Free-form prompts get a scenario built from the design itself: any pushbutton is pressed, then the simulator waits for the status line the model declared.

With Docker, which bakes the toolchain and a warm build cache:

```
docker build -t circuitmind .
docker run --rm -e WOKWI_CLI_TOKEN circuitmind reference T01_blink
```

### Rebuilding the catalogue

```
python tools/extract_catalogue.py > catalogue/parts.json
```

The catalogue is whatever `wokwi-cli lint` accepts. Each part's pin list comes from lint's own error output, so it cannot drift from what the simulator validates.

### Tests

```
python -m pytest -q
```

CI runs unit tests and lint only. It never runs a simulation.

## What is not done yet

- The benchmark is 5 tasks. It needs 25 and repeated runs before the numbers mean much.
- The engine runs on a laptop, not a server, so the live workspace is up only when the laptop is.
- The simulator checks logic and wiring. It does not check current draw or power limits, and the guide says so.
- The system is ESP32 DevKit v1 only.

## Licence

MIT.
