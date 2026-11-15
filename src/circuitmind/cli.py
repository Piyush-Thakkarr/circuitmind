"""Command-line entry points."""

from __future__ import annotations

import json
import os
import shutil
import time
from pathlib import Path

import typer
import yaml

from . import catalogue as cat_mod
from .harness import run_ladder
from .ir import Design
from .loop import run_generation
from .providers import get_provider

app = typer.Typer(no_args_is_help=True, add_completion=False)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RESULTS = ROOT / "benchmark" / "results"
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


@app.command()
def generate(
    request: str = typer.Argument(..., help="What to build, in plain English."),
    task: str = typer.Option(None, help="Benchmark task id; uses its scenario and timeout for simulation."),
    provider: str = typer.Option("gemini", help="Model provider."),
    attempts: int = typer.Option(3, help="Maximum attempts."),
    simulate: bool = typer.Option(False, help="Run the simulation rung (needs WOKWI_CLI_TOKEN, spends budget)."),
    grounded: bool = typer.Option(True, help="Include the part catalogue in the prompt."),
    feedback: bool = typer.Option(True, help="Send failures back to the model on retry."),
    serial_monitor: bool = typer.Option(False, help="Inject $serialMonitor connections."),
) -> None:
    """Generate a design from REQUEST and verify it, retrying on failure."""
    cat = cat_mod.load()
    scenario = None
    timeout_ms = 5000
    if task:
        t, tdir = _load_task(task)
        scenario = tdir / "scenario.yaml"
        timeout_ms = int(t["timeout_ms"])
        if request.strip() == "-":
            request = t["prompt"]
    if simulate and scenario is None:
        raise typer.BadParameter("--simulate needs --task so there is a scenario to assert against")
    if simulate and not os.environ.get("WOKWI_CLI_TOKEN"):
        raise typer.BadParameter("--simulate needs WOKWI_CLI_TOKEN in the environment")

    from .scope import message, screen

    refusal = screen(request)
    if refusal:
        typer.echo(message(refusal))
        raise typer.Exit(2)

    prov = get_provider(provider)
    workdir = RUNS / "generate" / time.strftime("%Y%m%d-%H%M%S")
    typer.echo(f"request:  {request.strip()}")
    typer.echo(f"model:    {getattr(prov, 'model', prov.name)}   catalogue: {cat.hash}   attempts: {attempts}")
    typer.echo("")

    def on_event(kind, p):
        if kind == "model.start":
            typer.echo(f"attempt {p['attempt']}")
            typer.echo("  asking model ...", nl=False)
        elif kind == "model.done":
            typer.echo(f" {p['latency_s']:.1f}s  ({p['tokens_in']} in / {p['tokens_out']} out)")
        elif kind == "rung":
            mark = "PASS" if p["passed"] else "FAIL"
            typer.echo(f"  {p['rung']:12} {mark}  {p['seconds']:5.1f}s  {p['summary']}")
        elif kind == "attempt.done":
            if not p["passed"]:
                typer.echo(f"  -> failed at {p['failed_rung']}; sending feedback to model")
            typer.echo("")

    res = run_generation(request, prov, cat, workdir, max_attempts=attempts, simulate=simulate,
                         scenario=scenario, timeout_ms=timeout_ms, grounded=grounded,
                         use_feedback=feedback, inject_serial_monitor=serial_monitor, on_event=on_event)

    fin = res.final
    if fin and not fin.passed and fin.outcome.results:
        last = fin.outcome.results[-1]
        typer.echo("last error:")
        for line in last.detail.splitlines()[:8]:
            typer.echo(f"  {line}")
        typer.echo("")
    tin, tout = res.tokens()
    verdict = "VERIFIED" if res.passed else "NOT VERIFIED"
    typer.echo(f"outcome: {verdict}  after {len(res.attempts)} attempt(s)   tokens {tin} in / {tout} out")
    typer.echo(f"run dir: {workdir}")
    if res.passed and fin and fin.design:
        d = fin.design
        typer.echo("")
        typer.echo("parts:")
        for p in d.parts:
            a = ", ".join(f"{k}={v}" for k, v in p.attrs.items())
            typer.echo(f"  {p.id:10} {p.type:34} {a}")
        typer.echo("wiring:")
        for a, b in d.connections:
            typer.echo(f"  {a}  ->  {b}")
    raise typer.Exit(0 if res.passed else 1)


@app.command()
def bench(
    config: str = typer.Argument(..., help="A, B, C or D."),
    provider: str = typer.Option("gemini", help="Model provider."),
    only: str = typer.Option(None, help="Comma-separated task ids to run; default all."),
    results: str | None = typer.Option(None, help="Where results JSON goes (default benchmark/results)."),
    label: str = typer.Option("", help="Suffix for the results file, for example run1 -> A_run1.json."),
    yes: bool = typer.Option(False, "--yes", help="Spend the estimated simulation time without asking."),
    merge: bool = typer.Option(False, "--merge", help="With --only: put these tasks' rows into the existing "
                               "results file in place of the old ones (repairing tasks that hit an engine error)."),
) -> None:
    """Run one benchmark configuration across the task suite. Prints the cost first and asks."""
    from .bench import (
        CONFIGS,
        TaskResult,
        estimate_sim_ms,
        load_tasks,
        merge_results,
        results_path,
        run_task,
        summary_table,
        write_results,
    )

    results_dir = Path(results) if results else DEFAULT_RESULTS

    config = config.upper()
    if config not in CONFIGS:
        raise typer.BadParameter("config must be A, B, C or D")
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        raise typer.BadParameter("bench needs WOKWI_CLI_TOKEN; every config simulates at least once per task")
    if merge and (not only or not results_path(results_dir, config, label).exists()):
        raise typer.BadParameter("--merge needs --only and an existing results file for this config and label")
    os.environ["CIRCUITMIND_WAIT_FOR_QUOTA"] = "1"  # a sweep waits out the daily token window; the web app never does
    cat = cat_mod.load()
    prov = get_provider(provider)
    tasks = load_tasks(TASKS, only.split(",") if only else None)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    cfg = CONFIGS[config]
    typer.echo(f"config {config}: grounded={cfg['grounded']} feedback={cfg['use_feedback']} "
               f"attempts={cfg['max_attempts']} sim_in_loop={cfg['sim_in_loop']}")
    typer.echo(f"model {getattr(prov, 'model', prov.name)}, {len(tasks)} tasks, catalogue {cat.hash}")
    likely, worst = estimate_sim_ms(config, tasks)
    requests = len(tasks) * cfg["max_attempts"]
    typer.echo(f"cost: about {likely / 60000:.1f} simulated minutes, {worst / 60000:.1f} at worst, "
               f"of the 50 a month on the free tier; up to {requests} model requests "
               f"(Groq free tier: 200K tokens a day, enough for A and B together, or C, or D)")
    if not yes and not typer.confirm("Spend it?", default=False):
        typer.echo("stopped before spending anything")
        raise typer.Exit(0)
    typer.echo("")

    def run_one(t: dict, tdir: Path, wd: Path) -> TaskResult:
        typer.echo(f"{t['id']}", nl=False)
        marks: list[str] = []

        def ev(kind, p):
            if kind == "attempt.done":
                marks.append("ok" if p["passed"] else p["failed_rung"])
            elif kind == "final_sim":
                marks.append("sim-ok" if p["passed"] else "sim-fail")

        try:
            r = run_task(config, t, tdir, prov, cat, wd, on_event=ev)
        except Exception as e:  # noqa: BLE001 - one task must not kill the sweep
            r = TaskResult(task_id=t["id"], passed=False, attempts=0, failed_rung="error",
                           tokens_in=0, tokens_out=0, sim_ms=0, seconds=0.0)
            marks.append(f"error: {str(e)[:80]}")
        typer.echo(f"  {'PASS' if r.passed else 'FAIL':4}  attempts={r.attempts}  [{' > '.join(marks)}]  "
                   f"{r.seconds:4.0f}s  sim {r.sim_ms/1000:.0f}s")
        return r

    rows: dict[str, TaskResult] = {}
    for t, tdir in tasks:
        rows[t["id"]] = run_one(t, tdir, RUNS / "bench" / stamp / config / t["id"])

    # A task that ended with rung "error" never reached the model or the checks (the
    # model service failed, usually a quota the wait could not sit out). That says
    # nothing about the design, so each such task gets one more go before the file is written.
    errored = [(t, tdir) for t, tdir in tasks if rows[t["id"]].failed_rung == "error"]
    if errored:
        typer.echo("")
        typer.echo(f"{len(errored)} task(s) hit an engine error, not a model failure; running them once more")
        for t, tdir in errored:
            rows[t["id"]] = run_one(t, tdir, RUNS / "bench" / stamp / config / f"{t['id']}_again")

    row_list = list(rows.values())
    if merge:
        p = merge_results(results_path(results_dir, config, label), row_list)
    else:
        p = write_results(results_dir, config, getattr(prov, "model", prov.name), cat.hash, row_list, label=label)
    typer.echo("")
    n = len(row_list)
    at1 = sum(1 for r in row_list if r.passed and r.passed_attempt == 1)
    typer.echo(f"pass@1 {at1}/{n}, pass@3 {sum(r.passed for r in row_list)}/{n}. wrote {p}")
    still = [r.task_id for r in row_list if r.failed_rung == "error"]
    if still:
        typer.echo(f"still an engine error, not counted as a model result: {', '.join(still)}. "
                   f"Run them again with --only {','.join(still)} --merge")
    typer.echo("")
    typer.echo(summary_table(results_dir))


@app.command()
def serve(
    host: str = "127.0.0.1",
    port: int = 8000,
    tunnel: bool = typer.Option(False, help="Also open a public https address with cloudflared and print a link to share."),
) -> None:
    """Start the HTTP API for the web app."""
    import uvicorn

    from .tunnel import QuickTunnel, share_link

    qt = None
    if tunnel:
        qt = QuickTunnel(port)
        try:
            url = qt.start()
        except RuntimeError as e:
            typer.echo(str(e), err=True)
            raise typer.Exit(1)
        typer.echo("")
        typer.echo(f"engine address: {url}")
        typer.echo(f"share this link: {share_link(url)}")
        typer.echo("the address changes every time this command starts; keep this window open")
        typer.echo("")
    try:
        uvicorn.run("circuitmind.api:app", host=host, port=port, log_level="info")
    finally:
        if qt:
            qt.stop()


@app.command()
def report(
    results: str | None = typer.Option(None, help="Results folder (default benchmark/results)."),
    runs: str = typer.Option("", help="Comma-separated runs/bench/<stamp> folders, for failure categories."),
) -> None:
    """Print the write-up tables from the benchmark results files."""
    from .report import render

    results_dir = Path(results) if results else DEFAULT_RESULTS
    run_dirs = [Path(r) for r in runs.split(",") if r.strip()]
    typer.echo(render(results_dir, run_dirs or None))
