"""Free-form scenarios: what they do and what they say they did."""

import yaml

from circuitmind.ir import Design
from circuitmind.scenario import build_scenario, led_should_be_on

FW = 'void setup() { Serial.begin(115200); } void loop() { Serial.println("DONE"); }'


def _design(parts, connections):
    return Design.model_validate({
        "board": "wokwi-esp32-devkit-v1",
        "parts": [{"id": i, "type": t, "attrs": {}} for i, t in parts],
        "connections": connections,
        "firmware": FW,
        "status_line": "DONE",
    })


LED_BTN = _design(
    [("btn1", "wokwi-pushbutton"), ("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
    [["btn1:1.l", "esp:D4"], ["btn1:2.l", "esp:GND.1"],
     ["esp:D13", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.2"]],
)


def test_button_is_pressed_and_status_line_awaited():
    s = build_scenario(LED_BTN, "when I press the button print DONE")
    doc = yaml.safe_load(s.yaml)
    kinds = [next(iter(step)) for step in doc["steps"]]
    assert kinds == ["delay", "set-control", "wait-serial"]
    assert doc["steps"][1]["set-control"]["part-id"] == "btn1"
    assert doc["steps"][2]["wait-serial"] == "DONE"
    assert s.checks == ["pressed btn1 and held it", "waited for the firmware to print DONE"]


def test_led_on_prompt_adds_pin_check_on_the_driving_gpio():
    s = build_scenario(LED_BTN, "press the button to turn on the LED and print DONE")
    doc = yaml.safe_load(s.yaml)
    last = doc["steps"][-1]["expect-pin"]
    assert last == {"part-id": "esp", "name": "D13", "value": 1}
    assert "checked D13, which drives led1, was high after that line" in s.checks


def test_blinking_led_gets_no_pin_check():
    s = build_scenario(LED_BTN, "blink the LED when the button is pressed, print DONE")
    assert "expect-pin" not in s.yaml
    assert led_should_be_on("light the LED") and not led_should_be_on("light the LED and fade it")


def test_design_without_inputs_says_so():
    d = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
    s = build_scenario(d, "turn on an LED and print DONE")
    assert s.checks[0] == "waited for the firmware to print DONE"
    assert s.checks[-1] == "no inputs were exercised: the design has no pushbutton"
    assert "name: D2" in s.yaml
