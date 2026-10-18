import json
from pathlib import Path

import pytest

from circuitmind.harness.lint import run_lint

pytestmark = pytest.mark.skipif(
    __import__("shutil").which("wokwi-cli") is None, reason="wokwi-cli not installed"
)


def _write(tmp_path: Path, diagram: dict) -> Path:
    (tmp_path / "diagram.json").write_text(json.dumps(diagram))
    return tmp_path


def test_clean_diagram_passes(tmp_path):
    d = _write(tmp_path, {
        "version": 1, "author": "t", "editor": "wokwi",
        "parts": [{"type": "wokwi-esp32-devkit-v1", "id": "esp"}, {"type": "wokwi-led", "id": "l"}],
        "connections": [["l:A", "esp:D2", "", []], ["l:C", "esp:GND.1", "", []]],
    })
    r = run_lint(d)
    assert r.passed and r.extra["errors"] == []


def test_invalid_pin_and_unknown_type_reported(tmp_path):
    d = _write(tmp_path, {
        "version": 1, "author": "t", "editor": "wokwi",
        "parts": [{"type": "wokwi-esp32-devkit-v1", "id": "esp"}, {"type": "wokwi-nope", "id": "x"}, {"type": "wokwi-led", "id": "l"}],
        "connections": [["l:ANODE", "esp:D99", "", []]],
    })
    r = run_lint(d)
    assert not r.passed
    rules = {e.split(":")[0] for e in r.extra["errors"]}
    assert {"invalid-pin", "unknown-part-type"} <= rules
    assert any("Valid pins: A, C" in e for e in r.extra["errors"])
