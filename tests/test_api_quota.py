"""With the month's simulation minutes gone, the engine still runs the free rungs and says so."""

import re
import time

from circuitmind import api, catalogue, quota
from circuitmind.guide import build_guide
from circuitmind.ir import Design
from circuitmind.providers import to_design_dict

REPLY = "API Error: You have used up your Free plan monthly CI minute quota."
NOTICE_RE = re.compile(
    r"^Simulation minutes for this month are used up \(resets \d{1,2} [A-Z][a-z]{2} \d{4}\)\. "
    r"Designs are checked up to compile and electrical rules only and are shown as unverified\.$"
)


def _open_engine(monkeypatch, tmp_path):
    """No sign-in, a simulator token, and a quota state file of our own."""
    monkeypatch.delenv("CIRCUITMIND_SUPABASE_URL", raising=False)
    monkeypatch.delenv("CIRCUITMIND_SUPABASE_ANON_KEY", raising=False)
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "wok_test")
    monkeypatch.setenv("CIRCUITMIND_QUOTA_FILE", str(tmp_path / "q.json"))


def _wait_for(seen):
    for _ in range(100):
        if seen:
            return
        time.sleep(0.01)
    raise AssertionError("the job never started")


def test_health_carries_the_quota_state(tmp_path, monkeypatch):
    _open_engine(monkeypatch, tmp_path)
    assert api.health()["quota"]["exhausted"] is False
    quota.mark_exhausted(REPLY)
    q = api.health()["quota"]
    assert q["exhausted"] is True
    assert NOTICE_RE.match(q["notice"])


def test_a_new_job_runs_free_rungs_only_and_the_reply_says_so(tmp_path, monkeypatch):
    _open_engine(monkeypatch, tmp_path)
    quota.mark_exhausted(REPLY)
    seen = []
    monkeypatch.setattr(api, "_run", lambda job_id, req, user, design_id: seen.append(req))
    out = api.generate(api.GenerateRequest(prompt="blink an LED and print BLINK", simulate=True), authorization=None)
    assert out["simulate"] is False
    assert NOTICE_RE.match(out["notice"])
    _wait_for(seen)
    assert seen[0].simulate is False
    assert api._job(out["job_id"])["notice"] == out["notice"]


def test_with_quota_left_nothing_changes(tmp_path, monkeypatch):
    _open_engine(monkeypatch, tmp_path)
    seen = []
    monkeypatch.setattr(api, "_run", lambda job_id, req, user, design_id: seen.append(req))
    out = api.generate(api.GenerateRequest(prompt="blink an LED and print BLINK", simulate=True), authorization=None)
    assert out["simulate"] is True and out["notice"] == ""
    _wait_for(seen)
    assert seen[0].simulate is True


def test_guide_note_calls_an_unsimulated_design_unverified():
    cat = catalogue.load()
    design = Design.model_validate(to_design_dict({
        "board": "wokwi-esp32-devkit-v1",
        "parts": [{"id": "led1", "type": "wokwi-led", "attrs": []}, {"id": "r1", "type": "wokwi-resistor", "attrs": []}],
        "connections": [{"from": "led1:A", "to": "r1:1"}, {"from": "r1:2", "to": "esp:D2"}, {"from": "led1:C", "to": "esp:GND.1"}],
        "firmware": 'void setup(){Serial.begin(115200);} void loop(){Serial.println("BLINK");}',
        "status_line": "BLINK",
    }))
    free = build_guide(design, cat, verified=True, simulated=False)["notes"]
    assert any("NOT run in the simulator" in n and "unverified" in n for n in free)
    simulated = build_guide(design, cat, verified=True, simulated=True)["notes"]
    assert any("passed logic and wiring checks in simulation" in n for n in simulated)
