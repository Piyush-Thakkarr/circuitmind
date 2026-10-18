# CircuitMind

Turns a plain-English electronics project into a circuit and firmware, then proves it works by running it in the Wokwi simulator before showing it to you.

## What it does

1. You describe a project. "Blink an LED once a second and print BLINK after two cycles."
2. The system generates a small design description: which parts, how they connect, and the firmware.
3. Every free check runs first: schema, `wokwi-cli lint`, compile with `arduino-cli`, and a consistency check between firmware pin numbers and the wiring.
4. Only a design that passes all of those is simulated. Simulation minutes are capped on Wokwi's free tier, so nothing reaches the simulator that could have been rejected for free.
5. If it fails, the error goes back to the model along with its previous attempt. Three tries, then it stops and tells you why.
6. If it passes, you get the wiring guide, the annotated code, a parts list, and a link to open the exact circuit in Wokwi.

## Status

The model is in the loop. `circuitmind generate` asks Gemini for a design, runs it up the ladder, and on failure sends the exact error and the previous attempt back for another try. Real runs are in `docs/demo-runs.md`, including one where the model needed three attempts and the feedback fixed it each time.

Five benchmark tasks exist with reference solutions that pass every free check. The simulation rung is wired up and untested against a live token. Next: token, then the four-version benchmark.

## Layout

```
benchmark/tasks/     one folder per task: task.yaml, scenario.yaml, reference/
catalogue/parts.json part types and their valid pins, extracted from wokwi-cli lint
docs/                demo-runs.md, real transcripts from the loop
src/circuitmind/     ir.py (the design schema), expand.py (schema to diagram.json),
                     catalogue.py, prompt.py, providers.py (Gemini, mock),
                     loop.py (generate, check, correct), harness/ (the ladder), cli.py
tools/               extract_catalogue.py, setup_toolchain.sh
tests/               unit tests, no simulation, no network
web/                 landing page
```

## Running

Requires Python 3.11+, `arduino-cli` with the ESP32 core, and `wokwi-cli`. `tools/setup_toolchain.sh` installs all of it.

```
pip install -e ".[dev]"
circuitmind tasks
circuitmind reference T01_blink --no-simulate     # free rungs only, no model

export GEMINI_API_KEY=...                          # free key from aistudio.google.com
circuitmind generate "blink an LED twice then print BLINK"
circuitmind generate - --task T03_servo_sweep      # use a benchmark task's prompt

export WOKWI_CLI_TOKEN=wok_...                     # from https://wokwi.com/dashboard/ci
circuitmind generate - --task T01_blink --simulate # full ladder, spends simulated seconds
```

Flags on `generate`: `--attempts N` (default 3), `--no-grounded` (leave the catalogue out of the prompt), `--no-feedback` (retry without sending the error back). Those two switches are what the benchmark's four versions are built from.

Or with Docker, which bakes the toolchain and a warm build cache:

```
docker build -t circuitmind .
docker run --rm -e WOKWI_CLI_TOKEN circuitmind reference T01_blink
```

## Rebuilding the catalogue

```
python tools/extract_catalogue.py > catalogue/parts.json
```

The catalogue is whatever `wokwi-cli lint` accepts. Each part's pin list comes from lint's own error output, so it cannot drift from what the simulator validates.

## Tests

```
python -m pytest -q
```

CI runs unit tests and lint only. It never runs a simulation.

## Licence

MIT.
