import json
import shutil
from pathlib import Path

import pytest

from circuitmind import catalogue
from circuitmind.loop import run_generation
from circuitmind.providers import MockProvider, to_design_dict

CAT = catalogue.load()
HAS_TOOLCHAIN = shutil.which("arduino-cli") is not None and shutil.which("wokwi-cli") is not None

GOOD = {
    "board": "wokwi-esp32-devkit-v1",
    "parts": [
        {"id": "led1", "type": "wokwi-led", "attrs": [{"key": "color", "value": "red"}]},
        {"id": "r1", "type": "wokwi-resistor", "attrs": [{"key": "value", "value": "220"}]},
    ],
    "connections": [
        {"from": "led1:A", "to": "r1:1"},
        {"from": "r1:2", "to": "esp:D2"},
        {"from": "led1:C", "to": "esp:GND.1"},
    ],
    "firmware": 'const int P=2; void setup(){Serial.begin(115200);pinMode(P,OUTPUT);} void loop(){digitalWrite(P,HIGH);delay(500);digitalWrite(P,LOW);delay(500);Serial.println("BLINK");}',
    "status_line": "BLINK",
}


def _bad_pin():
    w = json.loads(json.dumps(GOOD))
    w["connections"][1] = {"from": "r1:2", "to": "esp:D99"}
    return w


def _bad_type():
    w = json.loads(json.dumps(GOOD))
    w["parts"][0]["type"] = "wokwi-fake-led"
    return w


def test_wire_to_design_converts_attrs_and_connections():
    d = to_design_dict(GOOD)
    assert d["parts"][0]["attrs"] == {"color": "red"}
    assert d["connections"][0] == ("led1:A", "r1:1")


def test_unknown_part_fails_schema_without_toolchain(tmp_path):
    prov = MockProvider([_bad_type(), _bad_type(), _bad_type()])
    res = run_generation("blink", prov, CAT, tmp_path, max_attempts=3, simulate=False)
    assert not res.passed
    assert len(res.attempts) == 3
    assert all(a.failed_rung == "schema" for a in res.attempts)
    assert "wokwi-fake-led" in res.attempts[0].feedback


def test_retry_prompt_carries_previous_attempt_and_feedback(tmp_path):
    prov = MockProvider([_bad_type(), _bad_type()])
    run_generation("blink", prov, CAT, tmp_path, max_attempts=2, simulate=False)
    assert len(prov.calls) == 2
    first_user, second_user = prov.calls[0][1], prov.calls[1][1]
    assert "Previous design" not in first_user
    assert "Previous design" in second_user
    assert "wokwi-fake-led" in second_user
    assert "attempt 2 of 2" in second_user


def test_no_feedback_mode_sends_fresh_prompt_each_time(tmp_path):
    prov = MockProvider([_bad_type(), _bad_type()])
    run_generation("blink", prov, CAT, tmp_path, max_attempts=2, simulate=False, use_feedback=False)
    assert "Previous design" not in prov.calls[1][1]


def test_ungrounded_prompt_omits_catalogue(tmp_path):
    prov = MockProvider([_bad_type()])
    run_generation("blink", prov, CAT, tmp_path, max_attempts=1, simulate=False, grounded=False)
    assert "Catalogue of allowed part types" not in prov.calls[0][1]


def test_garbage_reply_counts_as_schema_failure(tmp_path):
    prov = MockProvider([{"nonsense": True}])
    res = run_generation("blink", prov, CAT, tmp_path, max_attempts=1, simulate=False)
    assert not res.passed and res.attempts[0].failed_rung == "schema"


@pytest.mark.skipif(not HAS_TOOLCHAIN, reason="arduino-cli and wokwi-cli required")
def test_bad_pin_then_fixed_passes_free_rungs(tmp_path):
    prov = MockProvider([_bad_pin(), GOOD])
    res = run_generation("blink", prov, CAT, tmp_path, max_attempts=3, simulate=False)
    assert res.passed
    assert len(res.attempts) == 2
    assert res.attempts[0].failed_rung == "lint"
    assert "D99" in res.attempts[0].feedback
    assert (Path(tmp_path) / "attempt_2" / "ir.json").exists()
    summary = json.loads((Path(tmp_path) / "summary.json").read_text())
    assert summary["passed"] is True and summary["attempts"][0]["failed_rung"] == "lint"
