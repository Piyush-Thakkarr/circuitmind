"""Build a Wokwi scenario for a free-form prompt, and say exactly what it checks.

Benchmark tasks have hand-written scenarios. A prompt typed into the web app
does not, so one is built from the design itself:

- press every pushbutton in the design
- wait for the status line the firmware promised to print
- if the prompt says an LED should turn on (and not blink, fade or toggle),
  check the GPIO that drives each LED is high once the status line has printed

The list of plain sentences in ``checks`` is shown to the user, so "verified"
never means more than what was actually exercised.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import yaml

from .harness.electrical import driving_board_pin
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


def _expect_pin(pin: str, value: int) -> str:
    return f"  - expect-pin:\n      part-id: esp\n      name: {pin}\n      value: {value}"


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
            pin = driving_board_pin(design, part.id, "A") or driving_board_pin(design, part.id, "C")
            if pin is None:
                continue
            steps.append(_expect_pin(pin, 1))
            checks.append(f"checked {pin}, which drives {part.id}, was high after that line")

    if not any(c.startswith("pressed") for c in checks):
        checks.append("no inputs were exercised: the design has no pushbutton")
    yaml = f"name: {name}\nversion: 1\nauthor: circuitmind\nsteps:\n" + "\n".join(steps) + "\n"
    return Scenario(yaml=yaml, checks=checks)


# Which part types a scenario control can drive. Used to map a scenario's part ids
# onto a model design that chose different ids.
CONTROL_TYPES: dict[str, tuple[str, ...]] = {
    "pressed": ("wokwi-pushbutton", "wokwi-analog-joystick"),
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


def adapt_to_design(scenario_yaml: str, design: Design) -> tuple[str, list[str], list[str]]:
    """Point a task scenario's set-control steps at the parts this design actually has.

    A scenario names parts (btn1, joy1). A model design may call its button
    something else. When exactly one design part can take the control, the step
    is retargeted and a note says so. When none can, that is a real failure:
    the design lacks a part the task needs, and the message says which.

    Returns (adapted yaml, notes, missing). Steps whose part-id already names a
    design part of a fitting type are left alone.
    """
    doc = yaml.safe_load(scenario_yaml) or {}
    types = {p.id: p.type for p in design.parts}
    notes: list[str] = []
    missing: list[str] = []
    remap: dict[str, str] = {}
    taken: set[str] = set()

    for step in doc.get("steps") or []:
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

    text = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True) if (notes or missing) else scenario_yaml
    return text, notes, sorted(set(missing))
