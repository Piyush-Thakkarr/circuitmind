"""Explain a failed run in plain words.

When every attempt fails, the web app shows one sentence per attempt (which
check, why), one suggestion, and four example prompts that are known to pass.
No raw check output on the first screen; the details stay available behind
a fold for anyone who wants them.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .loop import Attempt, RunResult

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "benchmark" / "tasks"

EXAMPLE_TASKS = ["T01_blink", "T03_servo_sweep", "T04_ultrasonic_distance", "T05_rgb_cycle"]
"""Tasks the model passed first time in the pilot run (benchmark/results/README.md)."""

_RUNG_WORDS = {
    "schema": "the design was not valid",
    "lint": "the wiring used pins or parts that do not exist",
    "compile": "the code did not compile",
    "consistency": "the code and the wiring disagreed about which pins are used",
    "electrical": "the wiring broke an electrical rule",
    "simulate": "it ran in the simulator but did not do what it promised",
    "model": "the model did not answer",
}

_SUGGESTIONS = {
    "schema": "Try naming the exact parts, for example 'a pushbutton and a red LED', and one clear thing to print.",
    "lint": "Try fewer parts, or pick parts from the examples below; the model made up pins it did not have.",
    "compile": "Try a simpler behaviour or a part from the examples; the model's code did not build.",
    "consistency": "Try saying which pin each part is on, for example 'an LED on GPIO 2'.",
    "electrical": "Try saying which supply or pin to use, for example 'servo powered from VIN'.",
    "simulate": "Try saying exactly what should print and when, for example 'print DONE after the second blink'.",
    "model": "The model service did not answer. Try again in a minute.",
}

_OUT_OF_REACH = "this needs a part the simulator does not have"


def _sentence(a: Attempt) -> str:
    rung = a.failed_rung or "model"
    why = _RUNG_WORDS.get(rung, "a check failed")
    summary = ""
    if a.outcome.results:
        last = a.outcome.results[-1]
        if not last.passed and last.summary:
            summary = last.summary.strip().rstrip(".")
    text = f"Attempt {a.n}: {why}"
    if summary and summary.lower() not in why:
        text += f" ({summary})"
    return text + "."


def _suggestion(res: RunResult) -> str:
    final = res.final
    if final is None:
        return _SUGGESTIONS["model"]
    if "not in catalogue" in final.feedback:
        return f"The design asked for a part the catalogue does not have, so {_OUT_OF_REACH}. Try the examples below."
    return _SUGGESTIONS.get(final.failed_rung or "model", _SUGGESTIONS["model"])


def example_prompts(tasks_dir: Path = TASKS) -> list[str]:
    out = []
    for tid in EXAMPLE_TASKS:
        f = tasks_dir / tid / "task.yaml"
        if f.exists():
            out.append(" ".join(yaml.safe_load(f.read_text())["prompt"].split()))
    return out


def explain_failure(res: RunResult) -> dict:
    """Plain-words account of a run that did not pass."""
    return {
        "attempts": [{"n": a.n, "rung": a.failed_rung or "model", "sentence": _sentence(a)} for a in res.attempts],
        "suggestion": _suggestion(res),
        "examples": example_prompts(),
    }
