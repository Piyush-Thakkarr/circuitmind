import json

import pytest
from pydantic import ValidationError

from circuitmind.ir import Design

GOOD = {
    "board": "wokwi-esp32-devkit-v1",
    "parts": [{"id": "led1", "type": "wokwi-led", "attrs": {"color": "red"}}],
    "connections": [["led1:A", "esp:D2"], ["led1:C", "esp:GND.1"]],
    "firmware": "void setup(){Serial.begin(115200);} void loop(){Serial.println(\"OK\");}",
    "status_line": "OK",
}


def test_good_design_validates():
    d = Design.model_validate(GOOD)
    assert d.board_pins_used() == {"D2", "GND.1"}


def test_duplicate_ids_rejected():
    bad = json.loads(json.dumps(GOOD))
    bad["parts"].append({"id": "led1", "type": "wokwi-led"})
    with pytest.raises(ValidationError, match="duplicate"):
        Design.model_validate(bad)


def test_reserved_board_id_rejected():
    bad = json.loads(json.dumps(GOOD))
    bad["parts"][0]["id"] = "esp"
    with pytest.raises(ValidationError, match="reserved"):
        Design.model_validate(bad)


def test_unknown_part_in_connection_rejected():
    bad = json.loads(json.dumps(GOOD))
    bad["connections"].append(["ghost:1", "esp:D4"])
    with pytest.raises(ValidationError, match="unknown part"):
        Design.model_validate(bad)


def test_status_line_must_appear_in_firmware():
    bad = json.loads(json.dumps(GOOD))
    bad["status_line"] = "NEVER_PRINTED"
    with pytest.raises(ValidationError, match="verbatim"):
        Design.model_validate(bad)


def test_bad_connection_format_rejected():
    bad = json.loads(json.dumps(GOOD))
    bad["connections"].append(["led1", "esp:D4"])
    with pytest.raises(ValidationError, match="partid:PIN"):
        Design.model_validate(bad)
