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
    passed_attempt: int | None = None


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


def estimate_sim_ms(config: str, tasks: list[tuple[dict, Path]]) -> tuple[int, int]:
    """(likely, worst case) simulated milliseconds a sweep of ``config`` can spend.

    Every configuration simulates the final design once; D may also simulate up
    to three times inside the loop. A scenario that passes stops early, so the
    likely figure takes half of each task's timeout per simulation; the worst
    case charges the full timeout every time (a timeout also costs one retry).
    """
    cfg = CONFIGS[config]
    sims = cfg["max_attempts"] if cfg["sim_in_loop"] else 1
    total_timeout = sum(int(t["timeout_ms"]) for t, _ in tasks)
    likely = total_timeout * sims // 2
    worst = total_timeout * sims * 2
    return likely, worst


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
                      sim_ms=sim_ms, seconds=time.time() - t0,
                      passed_attempt=res.passed_attempt if passed else None)


def results_path(results_dir: Path, config: str, label: str = "") -> Path:
    """``<config>.json``, or ``<config>_<label>.json`` when a label such as run1 is given."""
    return results_dir / (f"{config}_{label}.json" if label else f"{config}.json")


def _summary(config: str, model: str, cat_hash: str, rows: list[TaskResult], label: str) -> dict:
    n = len(rows)
    passed = sum(r.passed for r in rows)
    pass_at_1 = sum(1 for r in rows if r.passed and r.passed_attempt == 1)
    return {
        "config": config, "model": model, "catalogue": cat_hash,
        "when": time.strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": n, "passed": passed, "pass_rate": round(passed / n, 3) if n else 0.0,
        # pass@1: the first design passed every check. pass@3: any attempt the
        # configuration allows passed (A and B allow one, so both numbers agree).
        "pass_at_1": pass_at_1, "pass_at_3": passed,
        "mean_attempts_on_pass": round(sum(r.attempts for r in rows if r.passed) / passed, 2) if passed else None,
        "sim_ms_total": sum(r.sim_ms for r in rows),
        "tokens_in": sum(r.tokens_in for r in rows), "tokens_out": sum(r.tokens_out for r in rows),
        "rows": [r.__dict__ for r in rows],
        "label": label,
    }


def write_results(results_dir: Path, config: str, model: str, cat_hash: str, rows: list[TaskResult],
                  label: str = "") -> Path:
    """Write the results file for one sweep (see ``results_path``)."""
    results_dir.mkdir(parents=True, exist_ok=True)
    p = results_path(results_dir, config, label)
    p.write_text(json.dumps(_summary(config, model, cat_hash, rows, label), indent=2))
    return p


def merge_results(path: Path, rows: list[TaskResult]) -> Path:
    """Replace the rows of the tasks in ``rows`` inside an existing results file and redo its totals.

    For repairing a sweep in which a task ended with rung "error" (the model
    service failed, not the design): run that task again with ``--only`` and
    ``--merge``. The file records which tasks were redone and when.
    """
    d = json.loads(path.read_text())
    by_id = {r["task_id"]: r for r in d["rows"]}
    for r in rows:
        by_id[r.task_id] = r.__dict__
    merged = [TaskResult(**by_id[k]) for k in sorted(by_id)]
    data = _summary(d["config"], d["model"], d["catalogue"], merged, d.get("label", ""))
    data["first_written"] = d.get("first_written", d.get("when"))
    data["redone"] = d.get("redone", []) + [{"when": data["when"], "tasks": sorted(r.task_id for r in rows)}]
    path.write_text(json.dumps(data, indent=2))
    return path


def _pass_at_1(d: dict) -> int:
    """Read pass@1 from a results file; derive it for files written before the key existed."""
    if "pass_at_1" in d:
        return int(d["pass_at_1"])
    return sum(1 for r in d.get("rows", []) if r.get("passed") and r.get("attempts") == 1)


def result_files(results_dir: Path, config: str) -> list[Path]:
    """``A.json`` and every labelled run ``A_run1.json``, ``A_run2.json``, in name order."""
    files = [results_dir / f"{config}.json"] + sorted(results_dir.glob(f"{config}_*.json"))
    return [p for p in files if p.exists()]


def summary_table(results_dir: Path) -> str:
    """One row per results file; a labelled run shows as ``A run1``."""
    lines = ["| Config | Tasks | pass@1 | pass@3 | Mean attempts (on pass) | Sim seconds | Tokens in / out |",
             "|---|---|---|---|---|---|---|"]
    for c in "ABCD":
        for p in result_files(results_dir, c):
            d = json.loads(p.read_text())
            name = f"{c} {d['label']}" if d.get("label") else c
            lines.append(f"| {name} | {d['tasks']} | {_pass_at_1(d)}/{d['tasks']} | {d['passed']}/{d['tasks']} | "
                         f"{d['mean_attempts_on_pass'] if d['mean_attempts_on_pass'] is not None else '-'} | "
                         f"{d['sim_ms_total']/1000:.0f} | {d['tokens_in']} / {d['tokens_out']} |")
    return "\n".join(lines)
