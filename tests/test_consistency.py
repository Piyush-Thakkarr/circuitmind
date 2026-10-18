from circuitmind import catalogue
from circuitmind.harness.consistency import run_consistency
from circuitmind.ir import Design

CAT = catalogue.load()


def _design(firmware, connections):
    return Design.model_validate({
        "board": "wokwi-esp32-devkit-v1",
        "parts": [{"id": "led1", "type": "wokwi-led"}],
        "connections": connections,
        "firmware": firmware,
        "status_line": "OK",
    })


def test_matching_pins_pass():
    d = _design('void setup(){pinMode(2,OUTPUT);} void loop(){digitalWrite(2,HIGH);Serial.println("OK");}',
                [["led1:A", "esp:D2"], ["led1:C", "esp:GND.1"]])
    assert run_consistency(d, CAT).passed


def test_unwired_gpio_blocks():
    d = _design('void setup(){pinMode(5,OUTPUT);} void loop(){Serial.println("OK");}',
                [["led1:A", "esp:D2"], ["led1:C", "esp:GND.1"]])
    r = run_consistency(d, CAT)
    assert not r.passed and "GPIO [5]" in r.detail


def test_define_resolves():
    d = _design('#define LED 4\nvoid setup(){pinMode(LED,OUTPUT);} void loop(){Serial.println("OK");}',
                [["led1:A", "esp:D4"], ["led1:C", "esp:GND.1"]])
    assert run_consistency(d, CAT).passed


def test_unresolvable_passes_through():
    d = _design('void setup(){pinMode(cfg.pin,OUTPUT);} void loop(){Serial.println("OK");}',
                [["led1:A", "esp:D2"], ["led1:C", "esp:GND.1"]])
    r = run_consistency(d, CAT)
    assert r.passed and not r.extra["resolved"]


def test_output_on_input_only_pin_blocks():
    d = _design('void setup(){pinMode(34,OUTPUT);} void loop(){digitalWrite(34,HIGH);Serial.println("OK");}',
                [["led1:A", "esp:D34"], ["led1:C", "esp:GND.1"]])
    r = run_consistency(d, CAT)
    assert not r.passed and "input-only" in r.detail
