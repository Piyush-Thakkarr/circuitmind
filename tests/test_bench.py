"""Results files and the summary table report pass@1 and pass@3."""

import json

from circuitmind.bench import TaskResult, summary_table, write_results


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
