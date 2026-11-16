"""Results files and the summary table report pass@1 and pass@3."""

import json

from circuitmind.bench import (
    TaskResult,
    estimate_sim_ms,
    merge_results,
    result_files,
    results_path,
    summary_table,
    write_results,
)


def _row(tid, passed, attempts, passed_attempt=None, rung=""):
    return TaskResult(task_id=tid, passed=passed, attempts=attempts, failed_rung=rung, tokens_in=10,
                      tokens_out=5, sim_ms=1000, seconds=1.0, passed_attempt=passed_attempt)


def test_results_report_pass_at_1_and_pass_at_3(tmp_path):
    rows = [_row("T1", True, 1, 1), _row("T2", True, 3, 3), _row("T3", False, 3, None, "simulate")]
    p = write_results(tmp_path, "D", "model", "hash", rows)
    d = json.loads(p.read_text())
    assert d["pass_at_1"] == 1
    assert d["pass_at_3"] == 2
    assert d["passed"] == 2
    assert d["rows"][1]["passed_attempt"] == 3
    table = summary_table(tmp_path)
    assert "pass@1 | pass@3" in table
    assert "| D | 3 | 1/3 | 2/3 |" in table


def test_summary_table_derives_pass_at_1_for_older_result_files(tmp_path):
    old = {
        "config": "C", "tasks": 2, "passed": 2, "pass_rate": 1.0, "mean_attempts_on_pass": 1.5,
        "sim_ms_total": 2000, "tokens_in": 1, "tokens_out": 1,
        "rows": [{"task_id": "T1", "passed": True, "attempts": 1}, {"task_id": "T2", "passed": True, "attempts": 2}],
    }
    (tmp_path / "C.json").write_text(json.dumps(old))
    assert "| C | 2 | 1/2 | 2/2 |" in summary_table(tmp_path)


def test_labelled_runs_get_their_own_file_and_row(tmp_path):
    rows = [_row("T1", True, 1, 1)]
    p = write_results(tmp_path, "A", "m", "h", rows, label="run1")
    assert p.name == "A_run1.json"
    write_results(tmp_path, "A", "m", "h", rows, label="run2")
    write_results(tmp_path, "A", "m", "h", rows)
    assert [f.name for f in result_files(tmp_path, "A")] == ["A.json", "A_run1.json", "A_run2.json"]
    table = summary_table(tmp_path)
    assert "| A | 1 |" in table and "| A run1 | 1 |" in table and "| A run2 | 1 |" in table


def test_cost_estimate_counts_simulations_per_config():
    tasks = [({"timeout_ms": 6000}, None), ({"timeout_ms": 8000}, None)]  # 14 s of timeouts
    assert estimate_sim_ms("A", tasks) == (7000, 28000)   # one final simulation per task
    assert estimate_sim_ms("C", tasks) == (7000, 28000)   # retries are static, still one simulation
    assert estimate_sim_ms("D", tasks) == (21000, 84000)  # up to three simulations per task


def test_merge_results_replaces_rows_and_records_what_was_redone(tmp_path):
    rows = [_row("T1", True, 1, 1), _row("T2", False, 0, None, "error"), _row("T3", False, 0, None, "error")]
    p = write_results(tmp_path, "C", "model", "hash", rows, label="run1")
    assert p.name == "C_run1.json"
    assert results_path(tmp_path, "C", "run1") == p
    merge_results(p, [_row("T2", True, 2, 2)])
    d = json.loads(p.read_text())
    assert [r["task_id"] for r in d["rows"]] == ["T1", "T2", "T3"]
    assert d["passed"] == 2 and d["pass_at_1"] == 1 and d["pass_at_3"] == 2
    assert d["rows"][1]["failed_rung"] == "" and d["rows"][2]["failed_rung"] == "error"
    assert d["label"] == "run1" and d["first_written"]
    assert d["redone"] == [{"when": d["when"], "tasks": ["T2"]}]
    assert "| C run1 | 3 | 1/3 | 2/3 |" in summary_table(tmp_path)


def test_not_run_rows_are_left_out_of_the_totals_and_named_in_the_table(tmp_path):
    from circuitmind.bench import not_run_result
    from circuitmind.report import _cell

    rows = [_row("T1", True, 1, 1), not_run_result("T2", attempts=1, tokens_in=7, tokens_out=3), not_run_result("T3")]
    p = write_results(tmp_path, "C", "model", "hash", rows, label="run2")
    d = json.loads(p.read_text())
    assert d["tasks"] == 1 and d["passed"] == 1 and d["pass_at_1"] == 1
    assert d["not_run"] == ["T2", "T3"]
    assert d["rows"][1]["failed_rung"] == "quota" and d["rows"][1]["passed"] is False
    assert d["tokens_in"] == 17  # the model calls that happened are still counted
    assert "| C run2 (2 not run: quota) | 1 | 1/1 | 1/1 |" in summary_table(tmp_path)
    assert _cell(d["rows"][1]) == "not run (quota)"

    # after the reset the missing tasks are run again and merged in; the list shrinks
    merge_results(p, [_row("T2", True, 1, 1)])
    d = json.loads(p.read_text())
    assert d["not_run"] == ["T3"] and d["tasks"] == 2 and d["passed"] == 2
