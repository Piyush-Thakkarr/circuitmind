"""The bench command gives a task that hit an engine error one more go, and --merge repairs a results file."""

import json

from typer.testing import CliRunner

import circuitmind.bench as bench_mod
from circuitmind.bench import TaskResult, write_results
from circuitmind.cli import app


def _fake_run_task(calls):
    def run_task(config, task, tdir, provider, cat, workdir, on_event=None):
        calls.append(workdir.name)
        if len(calls) == 1:
            raise RuntimeError("groq daily quota exhausted")
        return TaskResult(task_id=task["id"], passed=True, attempts=1, failed_rung="", tokens_in=1,
                          tokens_out=1, sim_ms=0, seconds=0.1, passed_attempt=1)
    return run_task


class _Prov:
    name = model = "fake"


def test_bench_retries_an_engine_error_once(tmp_path, monkeypatch):
    calls: list[str] = []
    monkeypatch.setattr("circuitmind.cli.get_provider", lambda name: _Prov())
    monkeypatch.setattr(bench_mod, "run_task", _fake_run_task(calls))
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "x")
    monkeypatch.setattr("circuitmind.cli.RUNS", tmp_path / "runs")
    res = CliRunner().invoke(app, ["bench", "A", "--provider", "fake", "--only", "T01_blink", "--yes",
                                   "--results", str(tmp_path), "--label", "t"])
    assert res.exit_code == 0, res.output
    assert calls == ["T01_blink", "T01_blink_again"]
    assert "hit an engine error" in res.output
    d = json.loads((tmp_path / "A_t.json").read_text())
    assert d["passed"] == 1 and d["rows"][0]["failed_rung"] == ""


def test_bench_merge_needs_only_and_an_existing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "x")
    monkeypatch.setattr("circuitmind.cli.get_provider", lambda name: _Prov())
    res = CliRunner().invoke(app, ["bench", "A", "--provider", "fake", "--only", "T01_blink", "--yes", "--merge",
                                   "--results", str(tmp_path), "--label", "t"])
    assert res.exit_code != 0
    assert "--merge needs --only and an existing results file" in res.output

    calls: list[str] = []
    monkeypatch.setattr(bench_mod, "run_task", _fake_run_task(calls))
    monkeypatch.setattr("circuitmind.cli.RUNS", tmp_path / "runs")
    rows = [TaskResult("T01_blink", False, 0, "error", 0, 0, 0, 0.0), TaskResult("T02_x", True, 1, "", 1, 1, 0, 1.0, 1)]
    write_results(tmp_path, "A", "m", "h", rows, label="t")
    res = CliRunner().invoke(app, ["bench", "A", "--provider", "fake", "--only", "T01_blink", "--yes", "--merge",
                                   "--results", str(tmp_path), "--label", "t"])
    assert res.exit_code == 0, res.output
    d = json.loads((tmp_path / "A_t.json").read_text())
    assert d["tasks"] == 2 and d["passed"] == 2
    assert d["redone"][0]["tasks"] == ["T01_blink"]
