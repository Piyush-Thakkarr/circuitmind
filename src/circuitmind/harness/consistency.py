"""Rung 4d: firmware pins versus wiring.

Blocks only when it is certain: a GPIO literal appears in a pin-mode or
write/read call AND no wired board pin maps to that GPIO. Anything the check
cannot resolve is passed through.
"""

from __future__ import annotations

import re

from ..catalogue import INPUT_ONLY_BOARD_PINS, Catalogue
from ..ir import Design
from .types import Rung, RungResult

_CALL_RE = re.compile(
    r"\b(pinMode|digitalWrite|digitalRead|analogRead|analogWrite|ledcAttachPin|ledcAttach|tone)\s*\(\s*([A-Za-z_][A-Za-z0-9_]*|\d+)"
)
_DEFINE_RE = re.compile(r"#define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(\d+)\b")
_CONST_RE = re.compile(
    r"\b(?:const\s+)?(?:int|uint8_t|byte|unsigned\s+int)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(\d+)\s*;"
)


def _gpio_literals(firmware: str) -> tuple[set[int], bool]:
    """Return (gpio numbers used, fully_resolved)."""
    names: dict[str, int] = {}
    for m in _DEFINE_RE.finditer(firmware):
        names[m.group(1)] = int(m.group(2))
    for m in _CONST_RE.finditer(firmware):
        names[m.group(1)] = int(m.group(2))

    used: set[int] = set()
    resolved = True
    for m in _CALL_RE.finditer(firmware):
        arg = m.group(2)
        if arg.isdigit():
            used.add(int(arg))
        elif arg in names:
            used.add(names[arg])
        elif arg in {"LED_BUILTIN"}:
            used.add(2)
        else:
            resolved = False
    return used, resolved


def run_consistency(design: Design, cat: Catalogue) -> RungResult:
    used, resolved = _gpio_literals(design.firmware)
    wired_pins = design.board_pins_used()
    wired_gpio = {g for p in wired_pins if (g := cat.board_gpio(p)) is not None}

    problems: list[str] = []
    if resolved:
        unwired = sorted(used - wired_gpio)
        if unwired:
            problems.append(
                f"firmware uses GPIO {unwired} but nothing is wired to "
                f"{['D' + str(g) for g in unwired]} in the connections"
            )
    outputs_on_input_only = sorted(
        p for p in wired_pins if p in INPUT_ONLY_BOARD_PINS
        and (g := cat.board_gpio(p)) is not None
        and re.search(rf"\b(pinMode\s*\(\s*{g}\s*,\s*OUTPUT|digitalWrite\s*\(\s*{g}\b)", design.firmware)
    )
    if outputs_on_input_only:
        problems.append(f"pins {outputs_on_input_only} are input-only on the ESP32 and cannot drive output")

    if problems:
        return RungResult(
            rung=Rung.CONSISTENCY,
            passed=False,
            summary="firmware and wiring disagree",
            detail="\n".join(problems),
            extra={"used_gpio": sorted(used), "wired_gpio": sorted(wired_gpio), "resolved": resolved},
        )
    note = "" if resolved else "some pin arguments could not be resolved statically; passed through"
    return RungResult(
        rung=Rung.CONSISTENCY,
        passed=True,
        summary=note,
        extra={"used_gpio": sorted(used), "wired_gpio": sorted(wired_gpio), "resolved": resolved},
    )
