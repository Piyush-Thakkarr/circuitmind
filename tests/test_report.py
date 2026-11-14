"""The write-up tables: ranges across runs, per-task cells, failure categories."""

import json

from circuitmind.report import (
    classify_feedback,
    failure_categories,
    load_runs,
    per_task_table,
    render,
    summary_table,
)


def _data(config, label, rows):
    return {"config": config, "label": label, "tasks": len(rows), "passed": sum(r["passed"] for r in rows),
            "pass_at_1": sum(1 for r in rows if r["passed"] and r["attempts"] == 1),
            "sim_ms_total": 12000, "rows": rows}


def _row(t, passed, attempts, rung=""):
    return {"task_id": t, "passed": passed, "attempts": attempts, "failed_rung": rung,
            "passed_attempt": attempts if passed else None}


def test_summary_shows_min_to_max_across_runs(tmp_path):
    (tmp_path / "D_run1.json").write_text(json.dumps(_data("D", "run1", [_row("T1", True, 1), _row("T2", True, 3)])))
    (tmp_path / "D_run2.json").write_text(json.dumps(_data("D", "run2", [_row("T1", True, 1), _row("T2", False, 3, "simulate")])))
    (tmp_path / "A_run1.json").write_text(json.dumps(_data("A", "run1", [_row("T1", False, 1, "lint"), _row("T2", True, 1)])))
    runs = load_runs(tmp_path)
    table = summary_table(runs)
    assert "| A | bare model | 1 | 1 of 2 | 1 of 2 |" in table
    assert "| D | + retry on simulation errors too | 2 | 1 of 2 | 1 to 2 of 2 |" in table
    matrix = per_task_table(runs)
    assert "| T2 | pass | pass (3) / fail at simulate (3) |" in matrix
    assert "| T1 | fail at lint | pass / pass |" in matrix
    assert render(tmp_path).startswith("## Summary")


def test_feedback_is_put_in_the_first_matching_category():
    assert classify_feedback("[schema] FAILED: unknown part type(s)\nnot in catalogue: wokwi-motor") == "invented part or pin"
    assert classify_feedback("[consistency] FAILED\nfirmware uses GPIO [5] but nothing is wired to ['D5']") == "wrong GPIO in firmware"
    assert classify_feedback("[electrical] FAILED\nled1 has no resistor on either side") == "missing resistor"
    assert classify_feedback("[electrical] FAILED\nservo1 V+ is on 3V3") == "electrical rule"
    assert classify_feedback("[compile] FAILED\nfatal error: Servo.h: No such file") == "library or compile error"
    assert classify_feedback("[simulate] FAILED\ntimed out") == "logic error caught only by simulation"
    assert classify_feedback("") == "other"


def test_failure_categories_count_failed_attempts_per_config(tmp_path):
    d = tmp_path / "D" / "T01" / "attempt_1"
    d.mkdir(parents=True)
    (d / "feedback.txt").write_text("[compile] FAILED\nerror: expected ;")
    d2 = tmp_path / "D" / "T01" / "attempt_2"
    d2.mkdir()
    (d2 / "feedback.txt").write_text("[schema] passed\n[lint] passed\n[simulate] passed")
    cats = failure_categories([tmp_path])
    assert cats["D"]["library or compile error"] == 1
    assert sum(cats["D"].values()) == 1
