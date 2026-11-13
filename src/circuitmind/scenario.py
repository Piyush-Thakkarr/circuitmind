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

from .harness.electrical import driving_board_pin
from .ir import Design

_LED_ON_RE = re.compile(r"\b(turns? on|turn it on|lights? up|lights?|lit|switch(?:es)? on|glows?|led on)\b", re.I)
_LED_NOT_STEADY_RE = re.compile(r"\b(blink\w*|flash\w*|fade\w*|pwm|toggle\w*|cycle\w*|pulse\w*|dim\w*|breath\w*)\b", re.I)


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
