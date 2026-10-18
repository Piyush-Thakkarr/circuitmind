"""Command-line entry points."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import typer
import yaml

from . import catalogue as cat_mod
from .harness import run_ladder
from .ir import Design

app = typer.Typer(no_args_is_help=True, add_completion=False)

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / "benchmark" / "tasks"
RUNS = ROOT / "runs"


def _load_task(task_id: str) -> tuple[dict, Path]:
    tdir = TASKS / task_id
    if not tdir.exists():
        raise typer.BadParameter(f"no task at {tdir}")
    return yaml.safe_load((tdir / "task.yaml").read_text()), tdir


@app.command()
def reference(
    task_id: str,
    simulate: bool = typer.Option(True, help="Run the simulation rung (spends budget)."),
    serial_monitor: bool = typer.Option(False, help="Inject $serialMonitor connections."),
    keep: bool = typer.Option(True, help="Keep the run directory."),
) -> None:
    """Run TASK_ID's reference solution up the validation ladder."""
    task, tdir = _load_task(task_id)
    cat = cat_mod.load()
    design = Design.model_validate(json.loads((tdir / "reference" / "ir.json").read_text()))

    workdir = RUNS / "reference" / task_id
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True)

    scenario_src = tdir / "scenario.yaml"
    scenario = workdir / "scenario.yaml"
    shutil.copy(scenario_src, scenario)

    outcome = run_ladder(
        design,
        cat,
        workdir,
        scenario=scenario,
        timeout_ms=int(task["timeout_ms"]),
        simulate=simulate,
        inject_serial_monitor=serial_monitor,
    )
    for r in outcome.results:
        mark = "PASS" if r.passed else "FAIL"
        typer.echo(f"{mark:4} {r.rung.value:12} {r.seconds:5.1f}s  {r.summary}")
        if not r.passed and r.detail:
            for line in r.detail.splitlines():
                typer.echo(f"     {line}")
    typer.echo("")
    typer.echo(f"outcome: {'PASS' if outcome.passed else 'FAIL'}  (catalogue {cat.hash}, workdir {workdir})")
    if not keep:
        shutil.rmtree(workdir)
    raise typer.Exit(0 if outcome.passed else 1)


@app.command()
def tasks() -> None:
    """List benchmark tasks."""
    for tdir in sorted(TASKS.iterdir()):
        if (tdir / "task.yaml").exists():
            t = yaml.safe_load((tdir / "task.yaml").read_text())
            typer.echo(f"{t['id']:20} {t['category']:18} timeout {t['timeout_ms']} ms  {t['status_line']}")


@app.command()
def catalogue() -> None:
    """Print the catalogue block that goes into the model prompt."""
    cat = cat_mod.load()
    typer.echo(f"# catalogue snapshot {cat.hash}, {len(cat.parts)} parts")
    typer.echo(cat.prompt_block())
