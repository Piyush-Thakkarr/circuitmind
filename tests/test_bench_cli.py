"""The bench command gives a task that hit an engine error one more go, and --merge repairs a results file."""

import json
import re

from typer.testing import CliRunner

import circuitmind.bench as bench_mod
from circuitmind.bench import TaskResult, write_results
from circuitmind.cli import app

_ANSI = re.compile(r"\x1b\[[0-9;]*m")


def _plain(text: str) -> str:
    """Typer prints errors in a coloured Rich box when it thinks it has a terminal (it does on
    GitHub Actions): drop the colour codes and the box, and join the wrapped lines."""
    return " ".join(_ANSI.sub("", text).replace("│", " ").split())


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
    assert "--merge needs --only and an existing results file" in _plain(res.output)

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


def test_bench_stops_the_sweep_when_the_simulator_quota_is_used_up(tmp_path, monkeypatch):
    from circuitmind import quota
    from circuitmind.bench import not_run_result

    monkeypatch.setenv("WOKWI_CLI_TOKEN", "x")
    monkeypatch.setenv("CIRCUITMIND_QUOTA_FILE", str(tmp_path / "q.json"))
    monkeypatch.setattr("circuitmind.cli.get_provider", lambda name: _Prov())
    calls: list[str] = []

    def run_task(config, task, tdir, provider, cat, workdir, on_event=None):
        calls.append(task["id"])
        if len(calls) == 1:
            return TaskResult(task_id=task["id"], passed=True, attempts=1, failed_rung="", tokens_in=1,
                              tokens_out=1, sim_ms=5000, seconds=0.1, passed_attempt=1)
        quota.mark_exhausted("API Error: You have used up your Free plan monthly CI minute quota.")
        return not_run_result(task["id"], attempts=1)

    monkeypatch.setattr(bench_mod, "run_task", run_task)
    res = CliRunner().invoke(app, ["bench", "A", "--provider", "fake", "--yes", "--results", str(tmp_path),
                                   "--label", "t", "--only", "T01_blink,T02_button_serial,T03_servo_sweep"])
    assert res.exit_code == 0, res.output
    assert calls == ["T01_blink", "T02_button_serial"]  # the third task was never started
    out = _plain(res.output)
    assert "NOT RUN (quota)" in out
    assert "pass@1 1/1, pass@3 1/1" in out
    assert "2 task(s) not run (quota): T02_button_serial, T03_servo_sweep" in out
    assert "--only T02_button_serial,T03_servo_sweep --merge" in out
    d = json.loads((tmp_path / "A_t.json").read_text())
    assert d["tasks"] == 1 and d["passed"] == 1
    assert d["not_run"] == ["T02_button_serial", "T03_servo_sweep"]
    assert [r["failed_rung"] for r in d["rows"]] == ["", "quota", "quota"]


def test_bench_does_not_start_while_the_quota_is_known_to_be_used_up(tmp_path, monkeypatch):
    from circuitmind import quota

    monkeypatch.setenv("WOKWI_CLI_TOKEN", "x")
    monkeypatch.setenv("CIRCUITMIND_QUOTA_FILE", str(tmp_path / "q.json"))
    monkeypatch.setattr("circuitmind.cli.get_provider", lambda name: _Prov())
    quota.mark_exhausted("API Error: You have used up your Free plan monthly CI minute quota.")

    def run_task(*a, **k):
        raise AssertionError("no task may run")

    monkeypatch.setattr(bench_mod, "run_task", run_task)
    res = CliRunner().invoke(app, ["bench", "D", "--provider", "fake", "--yes", "--results", str(tmp_path),
                                   "--label", "t", "--only", "T01_blink"])
    assert res.exit_code == 2
    assert "not started" in res.output and "Nothing was run or spent" in res.output
    assert not (tmp_path / "D_t.json").exists()
