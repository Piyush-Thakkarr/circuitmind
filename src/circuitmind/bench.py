"""Benchmark runner: one configuration across the task suite.

Configurations:
  A  bare model: no catalogue, no retries
  B  grounded: catalogue in the prompt, no retries
  C  grounded + static feedback: retries on schema/lint/compile/consistency, simulate the final design once
  D  grounded + full feedback: retries on everything including simulation
"""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

import yaml

from .catalogue import Catalogue
from .harness import run_ladder
from .loop import RunResult, run_generation
from .providers import Provider

CONFIGS: dict[str, dict] = {
    "A": {"grounded": False, "use_feedback": False, "max_attempts": 1, "sim_in_loop": False},
    "B": {"grounded": True, "use_feedback": False, "max_attempts": 1, "sim_in_loop": False},
    "C": {"grounded": True, "use_feedback": True, "max_attempts": 3, "sim_in_loop": False},
    "D": {"grounded": True, "use_feedback": True, "max_attempts": 3, "sim_in_loop": True},
}


@dataclass
class TaskResult:
    task_id: str
    passed: bool
    attempts: int
    failed_rung: str
    tokens_in: int
    tokens_out: int
    sim_ms: int
    seconds: float


def load_tasks(tasks_dir: Path, only: list[str] | None = None) -> list[tuple[dict, Path]]:
    out = []
    for tdir in sorted(tasks_dir.iterdir()):
        f = tdir / "task.yaml"
        if not f.exists():
            continue
        t = yaml.safe_load(f.read_text())
        if only and t["id"] not in only:
            continue
        out.append((t, tdir))
    return out


def _sim_ms(res: RunResult) -> int:
    total = 0
    for a in res.attempts:
        for r in a.outcome.results:
            if r.rung.value == "simulate":
                total += int(r.extra.get("sim_ms_charged", 0))
    return total


def run_task(config: str, task: dict, tdir: Path, provider: Provider, cat: Catalogue, workdir: Path,
             on_event=None) -> TaskResult:
    cfg = CONFIGS[config]
    scenario = tdir / "scenario.yaml"
    timeout_ms = int(task["timeout_ms"])
    t0 = time.time()
    res = run_generation(
        task["prompt"], provider, cat, workdir,
        board=task["board"], max_attempts=cfg["max_attempts"],
        simulate=cfg["sim_in_loop"], scenario=scenario, timeout_ms=timeout_ms,
        grounded=cfg["grounded"], use_feedback=cfg["use_feedback"], on_event=on_event,
    )
    sim_ms = _sim_ms(res)
    passed = res.passed
    failed = res.final.failed_rung if res.final else "model"

    # A, B and C verify the final design in simulation exactly once, outside the loop.
    if passed and not cfg["sim_in_loop"] and res.final and res.final.design:
        fdir = workdir / "final_sim"
        if fdir.exists():
            shutil.rmtree(fdir)
        fdir.mkdir(parents=True)
        shutil.copy(scenario, fdir / "scenario.yaml")
        out = run_ladder(res.final.design, cat, fdir, scenario=fdir / "scenario.yaml",
                         timeout_ms=timeout_ms, simulate=True)
        passed = out.passed
        if not passed:
            failed = out.failed_rung.value if out.failed_rung else "simulate"
        for r in out.results:
            if r.rung.value == "simulate":
                sim_ms += int(r.extra.get("sim_ms_charged", 0))
        if on_event:
            on_event("final_sim", {"passed": passed})

    tin, tout = res.tokens()
    return TaskResult(task_id=task["id"], passed=passed, attempts=len(res.attempts),
                      failed_rung="" if passed else failed, tokens_in=tin, tokens_out=tout,
                      sim_ms=sim_ms, seconds=time.time() - t0)


def write_results(results_dir: Path, config: str, model: str, cat_hash: str, rows: list[TaskResult]) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    n = len(rows)
    passed = sum(r.passed for r in rows)
    data = {
        "config": config, "model": model, "catalogue": cat_hash,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": n, "passed": passed, "pass_rate": round(passed / n, 3) if n else 0.0,
        "mean_attempts_on_pass": round(sum(r.attempts for r in rows if r.passed) / passed, 2) if passed else None,
        "sim_ms_total": sum(r.sim_ms for r in rows),
        "tokens_in": sum(r.tokens_in for r in rows), "tokens_out": sum(r.tokens_out for r in rows),
        "rows": [r.__dict__ for r in rows],
    }
    p = results_dir / f"{config}.json"
    p.write_text(json.dumps(data, indent=2))
    return p


def summary_table(results_dir: Path) -> str:
    lines = ["| Config | Tasks | Passed | Pass rate | Mean attempts (on pass) | Sim seconds | Tokens in / out |",
             "|---|---|---|---|---|---|---|"]
    for c in "ABCD":
        p = results_dir / f"{c}.json"
        if not p.exists():
            continue
        d = json.loads(p.read_text())
        lines.append(f"| {c} | {d['tasks']} | {d['passed']} | {d['pass_rate']:.0%} | "
                     f"{d['mean_attempts_on_pass'] if d['mean_attempts_on_pass'] is not None else '-'} | "
                     f"{d['sim_ms_total']/1000:.0f} | {d['tokens_in']} / {d['tokens_out']} |")
    return "\n".join(lines)
