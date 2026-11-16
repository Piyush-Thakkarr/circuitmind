"""Build a Wokwi scenario for a free-form prompt, and say exactly what it checks.

Benchmark tasks have hand-written scenarios. A prompt typed into the web app
does not, so one is built from the design itself:

- press every pushbutton in the design
- wait for the status line the firmware promised to print
- if the prompt says an LED should turn on (and not blink, fade or toggle),
  check each LED is lit once the status line has printed

The list of plain sentences in ``checks`` is shown to the user, so "verified"
never means more than what was actually exercised.

This module also owns the ``expect-part`` step, which wokwi-cli does not know.
A scenario writes ``expect-part: {part-id: led1, state: on}`` and
``adapt_to_design`` turns it into the ``expect-pin`` wokwi-cli does know, with
the GPIO level worked out from the design's wiring: a GPIO on the anode side
lights the LED with HIGH, a GPIO on the cathode side lights it with LOW. Both
wirings light the LED on a desk, so both must pass the check.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import yaml

from .harness.electrical import gpio_drive
from .ir import Design

_LED_ON_RE = re.compile(
    r"\b(turns? on|turn it on|lights? up|lights?|lit|switch(?:es)? on|glows?|led on)\b", re.IGNORECASE
)
_LED_NOT_STEADY_RE = re.compile(
    r"\b(blink\w*|flash\w*|fade\w*|pwm|toggle\w*|cycle\w*|pulse\w*|dim\w*|breath\w*)\b", re.IGNORECASE
)


@dataclass
class Scenario:
    yaml: str
    checks: list[str] = field(default_factory=list)


def _press(part_id: str) -> str:
    return f"  - set-control:\n      part-id: {part_id}\n      control: pressed\n      value: 1"


def _expect_part(part_id: str, state: str) -> str:
    return f"  - expect-part:\n      part-id: {part_id}\n      state: {json.dumps(state)}"


def led_should_be_on(prompt: str) -> bool:
    """True when the prompt asks for an LED to be on and not for it to blink, fade or toggle."""
    return bool(_LED_ON_RE.search(prompt)) and not _LED_NOT_STEADY_RE.search(prompt)


def build_scenario(design: Design, prompt: str, *, name: str = "web") -> Scenario:
    steps = ["  - delay: 500ms"]
    checks: list[str] = []

    for part in design.parts:
        if part.type == "wokwi-pushbutton":
            steps.append(_press(part.id))
            checks.append(f"pressed {part.id} and held it")

    steps.append(f"  - wait-serial: {json.dumps(design.status_line)}")
    checks.append(f"waited for the firmware to print {design.status_line}")

    if led_should_be_on(prompt):
        for part in design.parts:
            if part.type != "wokwi-led":
                continue
            drive = gpio_drive(design, part.id, "A", "C")
            if drive is None:
                continue  # not driven by a GPIO (a relay contact, say): nothing to check
            gpio, active_high = drive
            steps.append(_expect_part(part.id, "on"))
            checks.append(
                f"checked {part.id} was on after that line: {gpio} {'high' if active_high else 'low'}, "
                f"the GPIO is on its {'anode' if active_high else 'cathode'} side"
            )

    if not any(c.startswith("pressed") for c in checks):
        checks.append("no inputs were exercised: the design has no pushbutton")
    yaml = f"name: {name}\nversion: 1\nauthor: circuitmind\nsteps:\n" + "\n".join(steps) + "\n"
    return Scenario(yaml=yaml, checks=checks)


# Which part types a scenario control can drive. Used to map a scenario's part ids
# onto a model design that chose different ids.
CONTROL_TYPES: dict[str, tuple[str, ...]] = {
    "pressed": ("wokwi-pushbutton", "wokwi-analog-joystick"),
    "value": ("wokwi-slide-switch",),
    "x": ("wokwi-analog-joystick",),
    "y": ("wokwi-analog-joystick",),
    "position": ("wokwi-potentiometer",),
    "accelX": ("wokwi-mpu6050",), "accelY": ("wokwi-mpu6050",), "accelZ": ("wokwi-mpu6050",),
    "rotationX": ("wokwi-mpu6050",), "rotationY": ("wokwi-mpu6050",), "rotationZ": ("wokwi-mpu6050",),
    "temperature": ("wokwi-dht22", "wokwi-mpu6050", "wokwi-ntc-temperature-sensor", "wokwi-ds18b20"),
    "humidity": ("wokwi-dht22",),
    "lux": ("wokwi-photoresistor-sensor",),
    "distance": ("wokwi-hc-sr04",),
    "motion": ("wokwi-pir-motion-sensor",),
}


# Parts an expect-part step can name, with the pin current enters and the pin it leaves.
# The RGB LED needs a `pin` (R, G or B) in the step to say which colour.
_LED_TERMINALS: dict[str, tuple[str | None, str]] = {
    "wokwi-led": ("A", "C"),
    "wokwi-rgb-led": (None, "COM"),
}


def _state_on(value: object) -> bool | None:
    """on/off, true/false, 1/0 -> True/False; None for anything else.

    PyYAML reads a bare `on` and `off` as booleans, so both forms arrive here.
    """
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("on", "1", "true", "high", "lit"):
        return True
    if text in ("off", "0", "false", "low", "dark"):
        return False
    return None


def _expand_expect_part(ep: dict, types: dict[str, str], design: Design) -> tuple[dict | None, str | None, str | None]:
    """Turn one expect-part step into an expect-pin step.

    Returns (expect_pin_step, note, problem). Exactly one of step and problem is set.
    The LED is found by its id when the design uses it, else by the GPIO the step
    names (`gpio`, the pin the request told the model to use), else by type when
    the design has exactly one such part.
    """
    pid = str(ep.get("part-id", ""))
    want = _state_on(ep.get("state"))
    if want is None:
        return None, None, f"expect-part {pid}: state must be on or off, not {ep.get('state')!r}"
    channel = ep.get("pin")
    hint = ep.get("gpio")
    hint = str(hint) if hint is not None else None

    def drive_of(part_id: str) -> tuple[str, bool] | None:
        hot, common = _LED_TERMINALS[types[part_id]]
        if hot is None:
            if not channel:
                return None
            hot = str(channel)
        return gpio_drive(design, part_id, hot, common)

    fitting = [i for i, t in types.items() if t in _LED_TERMINALS]
    if pid in types and types[pid] in _LED_TERMINALS:
        chosen = pid
    elif hint:
        on_hint = [i for i in fitting if (d := drive_of(i)) and d[0] == hint]
        if len(on_hint) != 1:
            kind = "an LED" if on_hint == [] else "one LED"
            have = f"; it has {len(on_hint)}" if on_hint else ""
            return None, None, f"the test expects {kind} driven from {hint} but the design has none wired to it{have}"
        chosen = on_hint[0]
    elif len(fitting) == 1:
        chosen = fitting[0]
    elif fitting:
        return None, None, (
            f"the test checks an LED called {pid} but the design has several ({', '.join(fitting)}) "
            f"and none is called {pid}; use the part names the request gives"
        )
    else:
        return None, None, f"the test checks an LED called {pid} but the design has no LED"

    label = f"{chosen}:{channel}" if channel else chosen
    drive = drive_of(chosen)
    if drive is None:
        if types[chosen] == "wokwi-rgb-led" and not channel:
            return None, None, f"expect-part {pid}: an RGB LED needs pin: R, G or B"
        return None, None, (
            f"{label} is not switched by one GPIO: wire one side of it, through its resistor, "
            "to a GPIO and the other side to a rail"
        )
    gpio, active_high = drive
    if hint and gpio != hint:
        return None, None, f"the request puts {label} on {hint} but the design drives it from {gpio}"
    level = 1 if want == active_high else 0
    side = "anode" if active_high else "cathode"
    if types[chosen] == "wokwi-rgb-led":
        side = f"{channel} pin" if active_high else "COM pin"
    note = f"{label} {'on' if want else 'off'} = {gpio} {'high' if level else 'low'} (GPIO on the {side} side)"
    if chosen != pid:
        note = f"{pid} -> {chosen}, " + note
    return {"expect-pin": {"part-id": "esp", "name": gpio, "value": level}}, note, None


def adapt_to_design(scenario_yaml: str, design: Design) -> tuple[str, list[str], list[str]]:
    """Point a task scenario at the parts this design actually has, and expand expect-part.

    A scenario names parts (btn1, joy1). A model design may call its button
    something else. When exactly one design part can take the control, the step
    is retargeted and a note says so. When none can, that is a real failure:
    the design lacks a part the task needs, and the message says which.

    ``expect-part`` steps (which wokwi-cli does not know) become ``expect-pin``
    steps with the level read off the wiring; see the module docstring.

    Returns (adapted yaml, notes, missing). Steps whose part-id already names a
    design part of a fitting type are left alone.
    """
    doc = yaml.safe_load(scenario_yaml) or {}
    types = {p.id: p.type for p in design.parts}
    notes: list[str] = []
    missing: list[str] = []
    remap: dict[str, str] = {}
    taken: set[str] = set()
    expanded = False

    steps = doc.get("steps") or []
    for i, step in enumerate(steps):
        if isinstance(step, dict) and "expect-part" in step:
            new_step, note, problem = _expand_expect_part(step["expect-part"] or {}, types, design)
            if problem:
                missing.append(problem)
            else:
                steps[i] = new_step
                notes.append(note)
                expanded = True
            continue
        if not isinstance(step, dict) or "set-control" not in step:
            continue
        sc = step["set-control"]
        pid = str(sc.get("part-id", ""))
        control = str(sc.get("control", sc.get("name", "")))
        fitting = CONTROL_TYPES.get(control)
        if fitting is None:
            continue  # a control we do not know; leave the step as written
        if pid in types and types[pid] in fitting:
            taken.add(pid)
            continue
        if pid in remap:
            sc["part-id"] = remap[pid]
            continue
        candidates = [i for i, t in types.items() if t in fitting and i not in taken and i not in remap.values()]
        if len(candidates) == 1:
            remap[pid] = candidates[0]
            taken.add(candidates[0])
            sc["part-id"] = candidates[0]
            notes.append(f"{pid} -> {candidates[0]}")
        else:
            kind = " or ".join(t.replace("wokwi-", "") for t in fitting)
            if candidates:
                missing.append(
                    f"the scenario drives a part called {pid} ({kind}) but the design has several "
                    f"({', '.join(candidates)}) and none is called {pid}; use the part names the request gives"
                )
            else:
                missing.append(f"the scenario needs a {kind} called {pid} but the design has no such part")

    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) if (notes or missing or expanded) else scenario_yaml
    return text, notes, sorted(set(missing))
