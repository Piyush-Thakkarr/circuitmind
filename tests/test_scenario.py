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


def test_led_on_prompt_adds_a_part_check_that_expands_to_the_driving_gpio():
    s = build_scenario(LED_BTN, "press the button to turn on the LED and print DONE")
    doc = yaml.safe_load(s.yaml)
    assert doc["steps"][-1]["expect-part"] == {"part-id": "led1", "state": "on"}
    assert "checked led1 was on after that line: D13 high, the GPIO is on its anode side" in s.checks
    text, notes, missing = adapt_to_design(s.yaml, LED_BTN)
    assert missing == [] and notes == ["led1 on = D13 high (GPIO on the anode side)"]
    assert yaml.safe_load(text)["steps"][-1] == {"expect-pin": {"part-id": "esp", "name": "D13", "value": 1}}


def test_blinking_led_gets_no_pin_check():
    s = build_scenario(LED_BTN, "blink the LED when the button is pressed, print DONE")
    assert "expect-part" not in s.yaml and "expect-pin" not in s.yaml
    assert led_should_be_on("light the LED") and not led_should_be_on("light the LED and fade it")


def test_design_without_inputs_says_so():
    d = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
    s = build_scenario(d, "turn on an LED and print DONE")
    assert s.checks[0] == "waited for the firmware to print DONE"
    assert s.checks[-1] == "no inputs were exercised: the design has no pushbutton"
    assert "part-id: led1" in s.yaml


def test_led_behind_a_relay_contact_is_not_checked():
    d = _design([("relay1", "wokwi-relay-module"), ("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D26", "relay1:IN"], ["relay1:NO", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
    s = build_scenario(d, "turn on the LED through the relay and print DONE")
    assert "expect-part" not in s.yaml



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


# expect-part: the LED's polarity comes from the wiring, not from the scenario.

LED_SCN = """steps:
  - wait-serial: "DONE"
  - expect-part:
      part-id: led1
      state: on
  - expect-part:
      part-id: led1
      state: off
"""

ANODE_SIDE = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                     [["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
# T18's run-1 design: anode on 3V3, resistor on the cathode side down to the GPIO, lit by LOW
CATHODE_SIDE = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                       [["led1:A", "esp:3V3"], ["led1:C", "r1:1"], ["r1:2", "esp:D2"]])


def _pins(text):
    return [s["expect-pin"] for s in yaml.safe_load(text)["steps"] if "expect-pin" in s]


def test_gpio_on_the_anode_side_lights_with_high():
    text, notes, missing = adapt_to_design(LED_SCN, ANODE_SIDE)
    assert missing == []
    assert _pins(text) == [{"part-id": "esp", "name": "D2", "value": 1}, {"part-id": "esp", "name": "D2", "value": 0}]
    assert notes == ["led1 on = D2 high (GPIO on the anode side)", "led1 off = D2 low (GPIO on the anode side)"]
    assert "expect-part" not in text


def test_gpio_on_the_cathode_side_lights_with_low():
    text, notes, missing = adapt_to_design(LED_SCN, CATHODE_SIDE)
    assert missing == []
    assert _pins(text) == [{"part-id": "esp", "name": "D2", "value": 0}, {"part-id": "esp", "name": "D2", "value": 1}]
    assert notes[0] == "led1 on = D2 low (GPIO on the cathode side)"


def test_yaml_reads_bare_on_as_a_boolean_and_both_forms_work():
    bare = LED_SCN.replace('state: on', 'state: on').replace('state: off', 'state: off')
    quoted = LED_SCN.replace('state: on', 'state: "on"').replace('state: off', 'state: "off"')
    assert yaml.safe_load(bare)["steps"][1]["expect-part"]["state"] is True
    assert _pins(adapt_to_design(bare, ANODE_SIDE)[0]) == _pins(adapt_to_design(quoted, ANODE_SIDE)[0])


def test_gpio_hint_picks_the_led_among_several_and_pins_it_to_the_requested_gpio():
    scn = ("steps:\n  - expect-part:\n      part-id: led_r\n      gpio: D25\n      state: on\n"
           "  - expect-part:\n      part-id: led_g\n      gpio: D27\n      state: off\n")
    d = _design([("a", "wokwi-led"), ("b", "wokwi-led"), ("r1", "wokwi-resistor"), ("r2", "wokwi-resistor")],
                [["esp:D25", "r1:1"], ["r1:2", "a:A"], ["a:C", "esp:GND.1"],
                 ["b:A", "esp:3V3"], ["b:C", "r2:1"], ["r2:2", "esp:D27"]])
    text, notes, missing = adapt_to_design(scn, d)
    assert missing == []
    assert _pins(text) == [{"part-id": "esp", "name": "D25", "value": 1}, {"part-id": "esp", "name": "D27", "value": 1}]
    assert notes == ["led_r -> a, a on = D25 high (GPIO on the anode side)",
                     "led_g -> b, b off = D27 high (GPIO on the cathode side)"]


def test_led_on_the_wrong_gpio_is_a_plain_failure():
    scn = "steps:\n  - expect-part:\n      part-id: led1\n      gpio: D4\n      state: on\n"
    _, notes, missing = adapt_to_design(scn, ANODE_SIDE)
    assert notes == []
    assert missing == ["the request puts led1 on D4 but the design drives it from D2"]
    d = _design([("x", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "x:A"], ["x:C", "esp:GND.1"]])
    _, _, missing = adapt_to_design(scn, d)
    assert missing == ["the test expects an LED driven from D4 but the design has none wired to it"]


def test_single_led_with_another_name_is_found_by_type():
    d = _design([("status_led", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "status_led:A"], ["status_led:C", "esp:GND.1"]])
    _, notes, missing = adapt_to_design(LED_SCN, d)
    assert missing == [] and notes[0] == "led1 -> status_led, status_led on = D2 high (GPIO on the anode side)"


def test_several_leds_and_no_gpio_hint_are_not_guessed():
    d = _design([("a", "wokwi-led"), ("b", "wokwi-led"), ("r1", "wokwi-resistor"), ("r2", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "a:A"], ["a:C", "esp:GND.1"],
                 ["esp:D4", "r2:1"], ["r2:2", "b:A"], ["b:C", "esp:GND.1"]])
    _, notes, missing = adapt_to_design(LED_SCN, d)
    assert notes == [] and len(missing) == 1 and "several (a, b)" in missing[0]


def test_led_not_on_any_gpio_and_no_led_are_plain_failures():
    rail_only = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                        [["esp:3V3", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:GND.1"]])
    _, _, missing = adapt_to_design(LED_SCN, rail_only)
    assert missing == [
        "led1 is not switched by one GPIO: wire one side of it, through its resistor, to a GPIO and the other side to a rail"
    ]
    none = _design([("btn1", "wokwi-pushbutton")], [["btn1:1.l", "esp:D4"], ["btn1:2.l", "esp:GND.1"]])
    _, _, missing = adapt_to_design(LED_SCN, none)
    assert missing == ["the test checks an LED called led1 but the design has no LED"]


def test_pull_up_on_the_same_rail_does_not_confuse_the_anode_side():
    # run 1's C T18 design: anode on 3V3, cathode through the resistor to D2, and the
    # DS18B20 pull-up from 3V3 to D15. Crossing that pull-up must not make D15 "drive" the LED.
    d = _design([("ds1", "wokwi-ds18b20"), ("rpu", "wokwi-resistor"), ("led1", "wokwi-led"), ("rled", "wokwi-resistor")],
                [["ds1:VCC", "esp:3V3"], ["ds1:GND", "esp:GND.1"], ["ds1:DQ", "esp:D15"],
                 ["rpu:1", "esp:3V3"], ["rpu:2", "ds1:DQ"],
                 ["led1:A", "esp:3V3"], ["led1:C", "rled:1"], ["rled:2", "esp:D2"]])
    text, notes, missing = adapt_to_design(LED_SCN, d)
    assert missing == []
    assert _pins(text) == [{"part-id": "esp", "name": "D2", "value": 0}, {"part-id": "esp", "name": "D2", "value": 1}]
    assert notes[0] == "led1 on = D2 low (GPIO on the cathode side)"


def test_led_between_two_gpios_cannot_be_checked():
    d = _design([("led1", "wokwi-led"), ("r1", "wokwi-resistor")],
                [["esp:D2", "r1:1"], ["r1:2", "led1:A"], ["led1:C", "esp:D4"]])
    _, _, missing = adapt_to_design(LED_SCN, d)
    assert len(missing) == 1 and "not switched by one GPIO" in missing[0]


def test_bad_state_is_reported():
    scn = "steps:\n  - expect-part:\n      part-id: led1\n      state: bright\n"
    _, _, missing = adapt_to_design(scn, ANODE_SIDE)
    assert missing == ["expect-part led1: state must be on or off, not 'bright'"]


RGB_SCN = ("steps:\n  - expect-part:\n      part-id: rgb1\n      pin: R\n      gpio: D25\n      state: on\n"
           "  - expect-part:\n      part-id: rgb1\n      pin: G\n      gpio: D26\n      state: off\n")


def _rgb(common_rail):
    return _design([("rgb1", "wokwi-rgb-led"), ("r1", "wokwi-resistor"), ("r2", "wokwi-resistor")],
                   [["esp:D25", "r1:1"], ["r1:2", "rgb1:R"], ["esp:D26", "r2:1"], ["r2:2", "rgb1:G"],
                    ["rgb1:COM", common_rail]])


def test_rgb_common_cathode_and_common_anode():
    text, notes, missing = adapt_to_design(RGB_SCN, _rgb("esp:GND.1"))
    assert missing == []
    assert _pins(text) == [{"part-id": "esp", "name": "D25", "value": 1}, {"part-id": "esp", "name": "D26", "value": 0}]
    assert notes[0] == "rgb1:R on = D25 high (GPIO on the R pin side)"
    text, notes, missing = adapt_to_design(RGB_SCN, _rgb("esp:3V3"))
    assert missing == []
    assert _pins(text) == [{"part-id": "esp", "name": "D25", "value": 1}, {"part-id": "esp", "name": "D26", "value": 0}]


def test_rgb_common_pin_on_a_gpio_lights_with_low():
    # odd but legal: the colour pin on 3V3 and the common pin switched by the GPIO
    d = _design([("rgb1", "wokwi-rgb-led"), ("r1", "wokwi-resistor")],
                [["esp:3V3", "r1:1"], ["r1:2", "rgb1:R"], ["rgb1:COM", "esp:D25"]])
    scn = "steps:\n  - expect-part:\n      part-id: rgb1\n      pin: R\n      state: on\n"
    text, notes, missing = adapt_to_design(scn, d)
    assert missing == [] and _pins(text) == [{"part-id": "esp", "name": "D25", "value": 0}]
    assert notes == ["rgb1:R on = D25 low (GPIO on the COM pin side)"]


def test_rgb_without_a_pin_is_reported():
    scn = "steps:\n  - expect-part:\n      part-id: rgb1\n      state: on\n"
    _, _, missing = adapt_to_design(scn, _rgb("esp:GND.1"))
    assert missing == ["expect-part rgb1: an RGB LED needs pin: R, G or B"]


def test_raw_expect_pin_steps_are_left_alone():
    scn = "steps:\n  - wait-serial: \"BEEP\"\n  - expect-pin:\n      part-id: esp\n      name: D13\n      value: 0\n"
    text, notes, missing = adapt_to_design(scn, ANODE_SIDE)
    assert text == scn and notes == [] and missing == []
