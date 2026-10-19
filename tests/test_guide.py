from circuitmind import catalogue
from circuitmind.guide import build_guide
from circuitmind.ir import Design

CAT = catalogue.load()


def test_guide_has_steps_parts_and_total():
    d = Design.model_validate({
        "board": "wokwi-esp32-devkit-v1",
        "parts": [
            {"id": "led1", "type": "wokwi-led", "attrs": {"color": "red"}},
            {"id": "r1", "type": "wokwi-resistor", "attrs": {"value": "220"}},
            {"id": "btn1", "type": "wokwi-pushbutton"},
        ],
        "connections": [["led1:A", "r1:1"], ["r1:2", "esp:D2"], ["led1:C", "esp:GND.1"],
                        ["btn1:1.l", "esp:D4"], ["btn1:2.l", "esp:GND.2"]],
        "firmware": 'void setup(){} void loop(){Serial.println("OK");}',
        "status_line": "OK",
    })
    g = build_guide(d, CAT)
    assert len(g["wiring"]) == 5
    assert g["wiring"][0].startswith("Connect")
    # signal connections come before power/ground ones
    assert "GND" not in g["wiring"][0]
    names = [p["name"] for p in g["parts"]]
    assert "ESP32 DevKit v1" in names and "Resistor 220 ohm" in names
    assert g["total_inr"] == sum(p["approx_inr"] for p in g["parts"])
    assert any("pull-up" in n for n in g["notes"])
