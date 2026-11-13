"""The failure explanation: one sentence per attempt, a suggestion, example prompts."""

import json

from circuitmind import catalogue
from circuitmind.failure import EXAMPLE_TASKS, example_prompts, explain_failure
from circuitmind.loop import run_generation
from circuitmind.providers import MockProvider

CAT = catalogue.load()

GOOD = {
    "board": "wokwi-esp32-devkit-v1",
    "parts": [
        {"id": "led1", "type": "wokwi-led", "attrs": [{"key": "color", "value": "red"}]},
        {"id": "r1", "type": "wokwi-resistor", "attrs": [{"key": "value", "value": "220"}]},
    ],
    "connections": [
        {"from": "led1:A", "to": "r1:1"}, {"from": "r1:2", "to": "esp:D2"}, {"from": "led1:C", "to": "esp:GND.1"},
    ],
    "firmware": 'void setup(){Serial.begin(115200);} void loop(){Serial.println("BLINK");}',
    "status_line": "BLINK",
}


def _bad_type():
    w = json.loads(json.dumps(GOOD))
    w["parts"][0]["type"] = "wokwi-drone-motor"
    return w


def test_schema_failures_become_sentences_and_a_part_suggestion(tmp_path):
    prov = MockProvider([_bad_type(), _bad_type(), _bad_type()])
    res = run_generation("a drone", prov, CAT, tmp_path, max_attempts=3, simulate=False)
    f = explain_failure(res)
    assert [a["n"] for a in f["attempts"]] == [1, 2, 3]
    assert f["attempts"][0]["rung"] == "schema"
    assert f["attempts"][0]["sentence"].startswith("Attempt 1: the design was not valid")
    assert "simulator does not have" in f["suggestion"]
    assert len(f["examples"]) == 4


def test_garbage_reply_gets_the_naming_suggestion(tmp_path):
    prov = MockProvider([{"nonsense": True}])
    res = run_generation("blink", prov, CAT, tmp_path, max_attempts=1, simulate=False)
    f = explain_failure(res)
    assert "naming the exact parts" in f["suggestion"]
    assert "raw" not in f["attempts"][0]["sentence"].lower()


def test_example_prompts_come_from_the_task_files():
    ex = example_prompts()
    assert len(ex) == len(EXAMPLE_TASKS) == 4
    assert any("BLINK" in p for p in ex)
    assert all("\n" not in p for p in ex)
