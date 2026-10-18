from circuitmind.expand import canonical_json, expand
from circuitmind.ir import Design

D = Design.model_validate({
    "board": "wokwi-esp32-devkit-v1",
    "parts": [
        {"id": "led1", "type": "wokwi-led", "attrs": {"color": "red"}},
        {"id": "r1", "type": "wokwi-resistor", "attrs": {"value": "220"}},
    ],
    "connections": [["led1:A", "r1:1"], ["r1:2", "esp:D2"], ["led1:C", "esp:GND.1"], ["r1:1", "esp:3V3"]],
    "firmware": "void setup(){} void loop(){Serial.println(\"X\");}",
    "status_line": "X",
})


def test_board_first_at_origin():
    d = expand(D)
    assert d["parts"][0]["id"] == "esp"
    assert d["parts"][0]["top"] == 0 and d["parts"][0]["left"] == 0


def test_layout_is_deterministic():
    assert canonical_json(expand(D)) == canonical_json(expand(D))


def test_wire_colours():
    conns = {(a, b): c for a, b, c, _ in expand(D)["connections"]}
    assert conns[("led1:C", "esp:GND.1")] == "black"
    assert conns[("r1:1", "esp:3V3")] == "red"
    assert conns[("r1:2", "esp:D2")] == "green"


def test_serial_monitor_injection_is_optional():
    assert not any("$serialMonitor" in a or "$serialMonitor" in b for a, b, _, _ in expand(D)["connections"])
    with_sm = expand(D, inject_serial_monitor=True)["connections"]
    assert with_sm[0][1] == "$serialMonitor:RX"


def test_required_top_level_fields():
    d = expand(D)
    assert set(d) == {"version", "author", "editor", "parts", "connections"}
