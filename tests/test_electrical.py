"""The electrical rung: each rule, and every reference design must pass it."""

import json
from pathlib import Path

from circuitmind import catalogue
from circuitmind.harness.electrical import run_electrical
from circuitmind.harness.types import Rung
from circuitmind.ir import Design

CAT = catalogue.load()
TASKS = Path(__file__).resolve().parents[1] / "benchmark" / "tasks"
FW = 'void setup() { Serial.begin(115200); } void loop() { Serial.println("OK"); }'


def _design(parts, connections):
    return Design.model_validate({
        "board": "wokwi-esp32-devkit-v1",
        "parts": [{"id": i, "type": t, "attrs": {}} for i, t in parts],
        "connections": connections,
        "firmware": FW,
        "status_line": "OK",
    })


def _led(with_resistor=True, gpio="D2"):
    if with_resistor:
        return _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                       [[f"esp:{gpio}", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
    return _design([("led1", "wokwi-led")], [[f"esp:{gpio}", "led1:A"], ["led1:C", "esp:GND.1"]])


def test_rung_sits_between_consistency_and_simulate():
    order = list(Rung)
    assert order.index(Rung.CONSISTENCY) < order.index(Rung.ELECTRICAL) < order.index(Rung.SIMULATE)


def test_good_led_passes_and_reports_current():
    r = run_electrical(_led(), CAT)
    assert r.passed
    assert r.extra["estimated_ma"] == 80 + 20


def test_led_without_resistor_fails():
    r = run_electrical(_led(with_resistor=False), CAT)
    assert not r.passed
    assert "led1 has no series resistor" in r.detail


def test_resistor_on_cathode_side_counts():
    d = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "led1:A"], ["led1:C", "r1:1"], ["r1:2", "esp:GND.1"]])
    assert run_electrical(d, CAT).passed


def test_rgb_colour_pin_without_resistor_fails():
    d = _design([("rgb1", "wokwi-rgb-led"), ("r1", "wokwi-resistor"), ("r2", "wokwi-resistor")],
                [["esp:D25", "r1:1"], ["r1:2", "rgb1:R"], ["esp:D26", "r2:1"], ["r2:2", "rgb1:G"],
                 ["esp:D27", "rgb1:B"], ["rgb1:COM", "esp:GND.1"]])
    r = run_electrical(d, CAT)
    assert not r.passed
    assert "rgb1 pin B has no series resistor" in r.detail
    assert "pin R" not in r.detail


def test_rails_shorted_fails():
    d = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"], ["esp:VIN", "esp:3V3"]])
    r = run_electrical(d, CAT)
    assert not r.passed
    assert "3V3 and VIN are wired together" in r.detail


def test_supply_shorted_to_ground_through_a_part_fails():
    d = _design([("pot1", "wokwi-potentiometer")],
                [["pot1:VCC", "esp:3V3"], ["pot1:GND", "esp:GND.1"], ["pot1:SIG", "esp:GND.2"], ["pot1:VCC", "pot1:SIG"]])
    r = run_electrical(d, CAT)
    assert not r.passed
    assert "3V3 and GND" in r.detail


def test_servo_on_3v3_fails_with_plain_fix():
    d = _design([("servo1", "wokwi-servo")],
                [["servo1:PWM", "esp:D18"], ["servo1:V+", "esp:3V3"], ["servo1:GND", "esp:GND.1"]])
    r = run_electrical(d, CAT)
    assert not r.passed
    assert "servo1 V+ is wired to 3V3" in r.detail and "VIN" in r.detail


def test_servo_on_vin_passes_and_unpowered_fails():
    ok = _design([("servo1", "wokwi-servo")],
                 [["servo1:PWM", "esp:D18"], ["servo1:V+", "esp:VIN"], ["servo1:GND", "esp:GND.1"]])
    assert run_electrical(ok, CAT).passed
    bad = _design([("us1", "wokwi-hc-sr04")],
                  [["us1:TRIG", "esp:D5"], ["us1:ECHO", "esp:D18"], ["us1:GND", "esp:GND.1"]])
    r = run_electrical(bad, CAT)
    assert not r.passed
    assert "us1 VCC is not connected to the 5 V supply" in r.detail


def test_led_driven_from_input_only_pin_through_resistor_fails():
    r = run_electrical(_led(gpio="D34"), CAT)
    assert not r.passed
    assert "led1 pin A is driven from D34, which is input-only" in r.detail


def test_two_servos_blow_the_usb_budget():
    d = _design([("s1", "wokwi-servo"), ("s2", "wokwi-servo")],
                [["s1:PWM", "esp:D18"], ["s1:V+", "esp:VIN"], ["s1:GND", "esp:GND.1"],
                 ["s2:PWM", "esp:D19"], ["s2:V+", "esp:VIN"], ["s2:GND", "esp:GND.2"]])
    r = run_electrical(d, CAT)
    assert not r.passed
    assert "over the 500 mA" in r.detail
    assert "s1 250 mA" in r.detail and "s2 250 mA" in r.detail
    assert r.extra["estimated_ma"] == 80 + 500


def test_several_problems_are_all_reported():
    d = _design([("led1", "wokwi-led"), ("servo1", "wokwi-servo")],
                [["esp:D34", "led1:A"], ["led1:C", "esp:GND.1"],
                 ["servo1:PWM", "esp:D18"], ["servo1:V+", "esp:3V3"], ["servo1:GND", "esp:GND.2"]])
    r = run_electrical(d, CAT)
    assert not r.passed
    assert r.summary == "3 electrical problem(s)"
    assert len(r.extra["problems"]) == 3


def test_every_reference_design_passes():
    refs = sorted(TASKS.glob("*/reference/ir.json"))
    assert len(refs) >= 20
    failures = {}
    for ref in refs:
        d = Design.model_validate(json.loads(ref.read_text()))
        r = run_electrical(d, CAT)
        if not r.passed:
            failures[ref.parent.parent.name] = r.detail
    assert failures == {}
