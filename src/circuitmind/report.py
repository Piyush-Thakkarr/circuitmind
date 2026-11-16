"""Turn benchmark results files into the tables for the write-up.

``circuitmind report`` reads every ``<config>_<label>.json`` (and a plain
``<config>.json``) in benchmark/results and prints Markdown: a summary with
pass@1 and pass@3 as min to max across runs, a per-task matrix, and, when run
folders are given, failure categories worked out from the feedback each
attempt got. Nothing here calls a model or the simulator.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .bench import CONFIGS, _pass_at_1, result_files

CONFIG_WORDS = {
    "A": "bare model",
    "B": "+ parts catalogue in the prompt",
    "C": "+ retry on schema, lint, compile, consistency, electrical errors",
    "D": "+ retry on simulation errors too",
}

# Order matters: the first pattern that matches names the category.
_CATEGORIES: list[tuple[str, re.Pattern[str]]] = [
    ("invented part or pin", re.compile(
        r"unknown part type|not in catalogue|unknown pin|no such pin|does not have a pin|invalid pin|"
        r"unknown-pin|unknown-part", re.IGNORECASE)),
    ("wrong GPIO in firmware", re.compile(r"\[consistency\] FAILED|firmware uses GPIO|nothing is wired to", re.IGNORECASE)),
    ("missing resistor", re.compile(r"no resistor|without a resistor|needs a series resistor", re.IGNORECASE)),
    ("electrical rule", re.compile(r"\[electrical\] FAILED", re.IGNORECASE)),
    ("library or compile error", re.compile(r"\[compile\] FAILED", re.IGNORECASE)),
    ("design shape", re.compile(r"\[schema\] FAILED|did not validate|must look like partid", re.IGNORECASE)),
    ("logic error caught only by simulation", re.compile(r"\[simulate\] FAILED", re.IGNORECASE)),
]


def classify_feedback(text: str) -> str:
    """The failure category of one attempt's feedback text."""
    for name, pat in _CATEGORIES:
        if pat.search(text or ""):
            return name
    return "other"


def load_runs(results_dir: Path) -> dict[str, list[dict]]:
    """{config: [results data per run, in file-name order]} for the configs that have files."""
    out: dict[str, list[dict]] = {}
    for c in "ABCD":
        datas = [json.loads(p.read_text()) for p in result_files(results_dir, c)]
        if datas:
            out[c] = datas
    return out


def _span(values: list[int]) -> str:
    lo, hi = min(values), max(values)
    return str(lo) if lo == hi else f"{lo} to {hi}"


def summary_table(runs: dict[str, list[dict]]) -> str:
    lines = ["| Version | What it has | Runs | pass@1 | pass@3 | Simulated seconds per run |",
             "|---|---|---|---|---|---|"]
    for c, datas in runs.items():
        n = datas[0]["tasks"]
        p1 = [_pass_at_1(d) for d in datas]
        p3 = [int(d["passed"]) for d in datas]
        sim = [int(d["sim_ms_total"]) // 1000 for d in datas]
        lines.append(f"| {c} | {CONFIG_WORDS[c]} | {len(datas)} | {_span(p1)} of {n} | {_span(p3)} of {n} | {_span(sim)} |")
    return "\n".join(lines)


def _cell(row: dict) -> str:
    if row.get("passed"):
        a = row.get("attempts") or 1
        return "pass" if a == 1 else f"pass ({a})"
    rung = row.get("failed_rung") or "?"
    a = row.get("attempts") or 0
    return f"fail at {rung}" + (f" ({a})" if a > 1 else "")


def per_task_table(runs: dict[str, list[dict]]) -> str:
    """One row per task; a cell lists the outcome of each run, separated by ' / '."""
    configs = list(runs)
    tasks: list[str] = []
    for datas in runs.values():
        for d in datas:
            for r in d["rows"]:
                if r["task_id"] not in tasks:
                    tasks.append(r["task_id"])
    tasks.sort()
    lines = ["| Task | " + " | ".join(configs) + " |", "|---|" + "---|" * len(configs)]
    for t in tasks:
        cells = []
        for c in configs:
            outcomes = []
            for d in runs[c]:
                row = next((r for r in d["rows"] if r["task_id"] == t), None)
                outcomes.append(_cell(row) if row else "-")
            cells.append(" / ".join(outcomes))
        lines.append(f"| {t} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


def failure_categories(run_dirs: list[Path]) -> dict[str, Counter]:
    """{config: Counter(category -> failed attempts)} from the feedback files under runs/bench/<stamp>/."""
    out: dict[str, Counter] = {}
    for base in run_dirs:
        for cfg_dir in sorted(p for p in base.iterdir() if p.is_dir() and p.name in "ABCD"):
            counter = out.setdefault(cfg_dir.name, Counter())
            for fb in cfg_dir.glob("*/attempt_*/feedback.txt"):
                text = fb.read_text(errors="replace")
                if "FAILED" not in text:
                    continue
                counter[classify_feedback(text)] += 1
    return out


def add_final_sim_failures(cats: dict[str, Counter], runs: dict[str, list[dict]]) -> dict[str, Counter]:
    """Count the final-simulation failures of A, B and C, which leave no feedback file.

    Those versions simulate the finished design once, outside the loop, so a
    design that fails there has no attempt feedback to classify; the results
    row says ``failed_rung: simulate``. D's simulation failures happen inside
    the loop and are already counted from their feedback files.
    """
    for c, datas in runs.items():
        cats.setdefault(c, Counter())  # every version gets a column, even one with no failures
        if CONFIGS[c]["sim_in_loop"]:
            continue
        n = sum(1 for d in datas for r in d["rows"] if not r.get("passed") and r.get("failed_rung") == "simulate")
        if n:
            cats[c]["logic error caught only by simulation"] += n
    return cats


def failure_table(cats: dict[str, Counter]) -> str:
    names = [n for n, _ in _CATEGORIES] + ["other"]
    configs = list(cats)
    lines = ["| Failure category (failed attempts) | " + " | ".join(configs) + " |", "|---|" + "---|" * len(configs)]
    for name in names:
        counts = [cats[c].get(name, 0) for c in configs]
        if any(counts):
            lines.append(f"| {name} | " + " | ".join(str(x) for x in counts) + " |")
    return "\n".join(lines)


def render(results_dir: Path, run_dirs: list[Path] | None = None) -> str:
    runs = load_runs(results_dir)
    if not runs:
        return "no results files found"
    note = ("pass@1: the first design passed every check including simulation. pass@3: some attempt passed, "
            "within the attempts the version allows (one for A and B, three for C and D). "
            "Ranges are min to max across runs.")
    parts = ["## Summary", "", summary_table(runs), "", note, "",
             "## Per task", "", per_task_table(runs), "",
             "Numbers in brackets are attempts used. Several runs are separated by a slash, in run order."]
    if run_dirs:
        cats = add_final_sim_failures(failure_categories(run_dirs), runs)
        if cats:
            how = ("Counted over every failed attempt in the run folders given, by the first thing the "
                   "feedback names, plus the final-simulation failures of A, B and C from the results files. "
                   "One task can appear up to three times in C and D.")
            parts += ["", "## Why attempts failed", "", failure_table(cats), "", how]
    return "\n".join(parts) + "\n"
