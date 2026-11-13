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


def test_comma_separated_declarations_resolve():
    d = _design('const int R = 25, G = 26, B = 27;\nvoid setup(){pinMode(R,OUTPUT);pinMode(G,OUTPUT);pinMode(B,OUTPUT);} void loop(){Serial.println("OK");}',
                [["led1:A", "esp:D25"], ["led1:C", "esp:GND.1"]])
    r = run_consistency(d, CAT)
    assert r.extra["resolved"] is True
    assert not r.passed and "GPIO [26, 27]" in r.detail


def test_static_setup_is_stripped():
    from circuitmind.harness.ladder import sanitize_firmware
    src = "static void setup(){}\nstatic void loop(){}\nstatic void helper(){}"
    out = sanitize_firmware(src)
    assert out.startswith("void setup()") and "\nvoid loop()" in out and "static void helper" in out


def test_helper_parameter_resolves_from_call_sites():
    fw = ('const int UP = 4; const int DOWN = 5;\n'
          'bool pressed(int pin, int &last) { int now = digitalRead(pin); last = now; return now == LOW; }\n'
          'void setup(){pinMode(UP,INPUT_PULLUP);pinMode(DOWN,INPUT_PULLUP);}\n'
          'void loop(){ int a=0,b=0; if (pressed(UP,a)) {} if (pressed(DOWN,b)) {} Serial.println("OK"); }')
    ok = _design(fw, [["led1:A", "esp:D4"], ["led1:C", "esp:D5"]])
    r = run_consistency(ok, CAT)
    assert r.passed and r.extra["resolved"] is True
    assert r.extra["used_gpio"] == [4, 5]
    bad = _design(fw, [["led1:A", "esp:D4"], ["led1:C", "esp:GND.1"]])
    r = run_consistency(bad, CAT)
    assert not r.passed and "GPIO [5]" in r.detail


def test_helper_with_unknown_call_site_argument_passes_through():
    fw = ('void blink(int pin) { digitalWrite(pin, HIGH); }\n'
          'void setup(){}\nvoid loop(){ blink(cfg.pin); Serial.println("OK"); }')
    r = run_consistency(_design(fw, [["led1:A", "esp:D2"], ["led1:C", "esp:GND.1"]]), CAT)
    assert r.passed and r.extra["resolved"] is False


def test_pin_array_resolves_to_every_element():
    fw = ('byte rows[4] = {13, 12, 14, 27};\n'
          'void setup(){ for (int i = 0; i < 4; i++) pinMode(rows[i], OUTPUT); }\n'
          'void loop(){ Serial.println("OK"); }')
    all_wired = [["led1:A", "esp:D13"], ["led1:C", "esp:D12"], ["led1:A", "esp:D14"], ["led1:C", "esp:D27"]]
    r = run_consistency(_design(fw, all_wired), CAT)
    assert r.passed and r.extra["resolved"] is True and r.extra["used_gpio"] == [12, 13, 14, 27]
    r = run_consistency(_design(fw, all_wired[:3]), CAT)
    assert not r.passed and "GPIO [27]" in r.detail


def test_servo_attach_counts_as_a_pin_use():
    fw = 'Servo s;\nvoid setup(){ s.attach(18); }\nvoid loop(){ Serial.println("OK"); }'
    r = run_consistency(_design(fw, [["led1:A", "esp:D18"], ["led1:C", "esp:GND.1"]]), CAT)
    assert r.passed and r.extra["used_gpio"] == [18]
    r = run_consistency(_design(fw, [["led1:A", "esp:D19"], ["led1:C", "esp:GND.1"]]), CAT)
    assert not r.passed and "GPIO [18]" in r.detail


def test_named_output_on_input_only_pin_blocks():
    fw = 'const int LED = 34;\nvoid setup(){pinMode(LED,OUTPUT);} void loop(){Serial.println("OK");}'
    r = run_consistency(_design(fw, [["led1:A", "esp:D34"], ["led1:C", "esp:GND.1"]]), CAT)
    assert not r.passed and "input-only" in r.detail


def test_input_only_pin_read_is_fine():
    fw = 'const int POT = 34;\nvoid setup(){} void loop(){ int v = analogRead(POT); Serial.println("OK"); }'
    r = run_consistency(_design(fw, [["led1:A", "esp:D34"], ["led1:C", "esp:GND.1"]]), CAT)
    assert r.passed


def test_every_reference_firmware_resolves():
    import json
    from pathlib import Path
    refs = sorted(Path(__file__).resolve().parents[1].glob("benchmark/tasks/*/reference/ir.json"))
    assert len(refs) >= 20
    unresolved = []
    for ref in refs:
        d = Design.model_validate(json.loads(ref.read_text()))
        r = run_consistency(d, CAT)
        assert r.passed, (ref, r.detail)
        if not r.extra["resolved"]:
            unresolved.append(ref.parent.parent.name)
    assert unresolved == []
