"""Free-form scenarios: what they do and what they say they did."""

import yaml

from circuitmind.ir import Design
from circuitmind.scenario import adapt_to_design, build_scenario, led_should_be_on

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



TASK_SCN = """name: t
version: 1
author: circuitmind
steps:
  - set-control:
      part-id: btn1
      control: pressed
      value: 1
  - wait-serial: "DONE"
  - set-control:
      part-id: btn1
      control: pressed
      value: 0
"""


def test_scenario_id_is_mapped_to_the_only_fitting_part():
    d = _design([("button_a", "wokwi-pushbutton"), ("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["button_a:1.l", "esp:D4"], ["button_a:2.l", "esp:GND.1"],
                 ["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.2"]])
    text, notes, missing = adapt_to_design(TASK_SCN, d)
    assert missing == [] and notes == ["btn1 -> button_a"]
    doc = yaml.safe_load(text)
    assert all(s["set-control"]["part-id"] == "button_a" for s in doc["steps"] if "set-control" in s)
    assert doc["steps"][1]["wait-serial"] == "DONE"


def test_matching_ids_leave_the_scenario_untouched():
    text, notes, missing = adapt_to_design(TASK_SCN, LED_BTN)
    assert text == TASK_SCN and notes == [] and missing == []


def test_missing_part_is_a_plain_failure_not_a_timeout():
    d = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
    _, notes, missing = adapt_to_design(TASK_SCN, d)
    assert notes == []
    assert missing == ["the scenario needs a pushbutton or analog-joystick called btn1 but the design has no such part"]


def test_two_candidates_are_not_guessed():
    d = _design([("a", "wokwi-pushbutton"), ("b", "wokwi-pushbutton")],
                [["a:1.l", "esp:D4"], ["a:2.l", "esp:GND.1"], ["b:1.l", "esp:D5"], ["b:2.l", "esp:GND.2"]])
    _, notes, missing = adapt_to_design(TASK_SCN, d)
    assert notes == [] and len(missing) == 1 and "several (a, b)" in missing[0]


def test_joystick_and_imu_controls_map_by_type():
    scn = ("steps:\n  - set-control:\n      part-id: joy1\n      control: y\n      value: 1\n"
           "  - set-control:\n      part-id: imu1\n      control: accelX\n      value: 0.7\n")
    d = _design([("stick", "wokwi-analog-joystick"), ("sensor", "wokwi-mpu6050")],
                [["stick:VERT", "esp:D34"], ["sensor:SDA", "esp:D21"]])
    _, notes, missing = adapt_to_design(scn, d)
    assert missing == [] and notes == ["joy1 -> stick", "imu1 -> sensor"]


def test_same_name_wrong_type_is_remapped():
    scn = "steps:\n  - set-control:\n      part-id: btn1\n      control: pressed\n      value: 1\n"
    d = _design([("btn1", "wokwi-led"), ("sw", "wokwi-pushbutton")],
                [["btn1:A", "esp:D2"], ["sw:1.l", "esp:D4"]])
    _, notes, missing = adapt_to_design(scn, d)
    assert notes == ["btn1 -> sw"] and missing == []
