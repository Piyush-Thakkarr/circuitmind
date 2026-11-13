"""Rung 4e: electrical rules. Pure Python, costs nothing.

Wiring facts that compile and consistency cannot see and that the simulator
does not model: supply rails shorted together, an LED with no series
resistor, a 5 V part fed from 3V3, an output driven from an input-only pin,
and a rough current total against what one USB port supplies. Every failure
is one plain sentence the model can act on.
"""

from __future__ import annotations

from collections import deque

from ..catalogue import INPUT_ONLY_BOARD_PINS, Catalogue
from ..ir import BOARD_ID, Design
from .types import Rung, RungResult

USB_LIMIT_MA = 500
"""What one USB 2.0 port supplies."""

BOARD_MA = 80
"""ESP32 DevKit v1 running without WiFi, rough."""

# Rough typical draw per part in mA, datasheet ballpark figures for budgeting only.
PART_MA: dict[str, int] = {
    "wokwi-led": 20,
    "wokwi-rgb-led": 60,
    "wokwi-resistor": 0,
    "wokwi-pushbutton": 0,
    "wokwi-slide-switch": 0,
    "wokwi-potentiometer": 1,
    "wokwi-buzzer": 30,
    "wokwi-servo": 250,  # SG90 moving; stall is higher
    "wokwi-dht22": 2,
    "wokwi-hc-sr04": 15,
    "wokwi-photoresistor-sensor": 1,
    "wokwi-ntc-temperature-sensor": 1,
    "wokwi-pir-motion-sensor": 1,
    "wokwi-mpu6050": 4,
    "wokwi-ds18b20": 2,
    "wokwi-lcd1602": 30,  # backlight on
    "wokwi-lcd2004": 40,
    "board-ssd1306": 20,
    "wokwi-7segment": 80,  # eight segments lit
    "wokwi-neopixel": 60,  # one pixel, full white
    "wokwi-membrane-keypad": 0,
    "wokwi-ky-040": 1,
    "wokwi-relay-module": 70,  # coil energised
    "wokwi-stepper-motor": 240,  # 28BYJ-48 class motor
    "wokwi-ir-receiver": 2,
    "wokwi-analog-joystick": 1,
    "wokwi-microsd-card": 100,
    "wokwi-ili9341": 150,
}
UNKNOWN_PART_MA = 20

# Parts whose supply pin must be on 5 V (VIN), not 3V3.
NEEDS_5V: dict[str, str] = {
    "wokwi-servo": "V+",
    "wokwi-hc-sr04": "VCC",
}

# Pins through which a GPIO drives the part. None of these may sit on an input-only pin.
DRIVEN_PINS: dict[str, set[str]] = {
    "wokwi-led": {"A", "C"},
    "wokwi-rgb-led": {"R", "G", "B"},
    "wokwi-buzzer": {"1", "2"},
    "wokwi-servo": {"PWM"},
    "wokwi-relay-module": {"IN"},
    "wokwi-neopixel": {"DIN"},
    "wokwi-stepper-motor": {"A-", "A+", "B+", "B-"},
    "wokwi-7segment": {"A", "B", "C", "D", "E", "F", "G", "DP", "DIG1", "DIG2", "DIG3", "DIG4"},
}

_RESISTOR = "wokwi-resistor"


def _rail(pin: str) -> str | None:
    """Name of the board supply rail a board pin belongs to, if any."""
    if pin.startswith("GND"):
        return "GND"
    if pin in ("VIN", "3V3"):
        return pin
    return None


class _Nets:
    """Electrical nets of a design: every pin that is wired together shares one net."""

    def __init__(self, design: Design) -> None:
        self._parent: dict[str, str] = {}
        for a, b in design.connections:
            self._union(a, b)
        self.types = {p.id: p.type for p in design.parts}
        self.members: dict[str, set[str]] = {}
        for ref in list(self._parent):
            self.members.setdefault(self._find(ref), set()).add(ref)
        # resistor bridges: net on one side <-> net on the other side
        self._bridges: dict[str, set[str]] = {}
        for p in design.parts:
            if p.type == _RESISTOR:
                n1, n2 = self.net(f"{p.id}:1"), self.net(f"{p.id}:2")
                if n1 and n2 and n1 != n2:
                    self._bridges.setdefault(n1, set()).add(n2)
                    self._bridges.setdefault(n2, set()).add(n1)

    def _find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def _union(self, a: str, b: str) -> None:
        ra, rb = self._find(a), self._find(b)
        if ra != rb:
            self._parent[ra] = rb

    def wired(self, ref: str) -> bool:
        return ref in self._parent

    def net(self, ref: str) -> str | None:
        return self._find(ref) if self.wired(ref) else None

    def pins_of(self, net: str) -> set[str]:
        return self.members.get(net, set())

    def board_pins(self, net: str) -> set[str]:
        return {r.split(":", 1)[1] for r in self.pins_of(net) if r.split(":", 1)[0] == BOARD_ID}

    def has_resistor(self, net: str) -> bool:
        return any(self.types.get(r.split(":", 1)[0]) == _RESISTOR for r in self.pins_of(net))

    def through_resistors(self, net: str) -> set[str]:
        """All nets reachable from `net` by crossing resistors."""
        seen = {net}
        todo = deque([net])
        while todo:
            n = todo.popleft()
            for m in self._bridges.get(n, ()):
                if m not in seen:
                    seen.add(m)
                    todo.append(m)
        return seen


def _rails_shorted(nets: _Nets) -> list[str]:
    out = []
    for net in nets.members:
        rails = sorted({r for p in nets.board_pins(net) if (r := _rail(p))})
        if len(rails) > 1:
            out.append(f"{' and '.join(rails)} are wired together; that is a short across the supply")
    return out


def _leds_without_resistor(design: Design, nets: _Nets) -> list[str]:
    out = []
    for p in design.parts:
        if p.type == "wokwi-led":
            a, c = nets.net(f"{p.id}:A"), nets.net(f"{p.id}:C")
            if a is None or c is None:
                continue  # unwired LED: lint or the simulator will say so
            if not (nets.has_resistor(a) or nets.has_resistor(c)):
                out.append(f"{p.id} has no series resistor; put a wokwi-resistor (220) between it and the GPIO")
        elif p.type == "wokwi-rgb-led":
            for pin in ("R", "G", "B"):
                n = nets.net(f"{p.id}:{pin}")
                if n is not None and not nets.has_resistor(n):
                    out.append(f"{p.id} pin {pin} has no series resistor; each colour pin needs its own")
    return out


def _wrong_supply(design: Design, nets: _Nets) -> list[str]:
    out = []
    for p in design.parts:
        pin = NEEDS_5V.get(p.type)
        if pin is None:
            continue
        n = nets.net(f"{p.id}:{pin}")
        board = nets.board_pins(n) if n else set()
        if "VIN" in board:
            continue
        if "3V3" in board:
            out.append(f"{p.id} {pin} is wired to 3V3; this part needs 5 V, wire it to VIN")
        else:
            out.append(f"{p.id} {pin} is not connected to the 5 V supply; wire it to VIN")
    return out


def _driven_from_input_only(design: Design, nets: _Nets) -> list[str]:
    out = []
    for p in design.parts:
        for pin in sorted(DRIVEN_PINS.get(p.type, ())):
            n = nets.net(f"{p.id}:{pin}")
            if n is None:
                continue
            for reach in nets.through_resistors(n):
                bad = sorted(nets.board_pins(reach) & INPUT_ONLY_BOARD_PINS)
                if bad:
                    out.append(
                        f"{p.id} pin {pin} is driven from {bad[0]}, which is input-only on the ESP32; "
                        f"use an output-capable pin such as D2, D4 or D5"
                    )
                    break
    return out


def _current_budget(design: Design) -> tuple[int, list[str]]:
    draws = [(p.id, PART_MA.get(p.type, UNKNOWN_PART_MA)) for p in design.parts]
    total = BOARD_MA + sum(ma for _, ma in draws)
    if total <= USB_LIMIT_MA:
        return total, []
    big = ", ".join(f"{pid} {ma} mA" for pid, ma in sorted(draws, key=lambda d: -d[1]) if ma >= 50)
    msg = (
        f"estimated draw {total} mA is over the {USB_LIMIT_MA} mA one USB port gives "
        f"(board {BOARD_MA} mA plus {big}); this needs a separate supply or fewer heavy parts"
    )
    return total, [msg]


def driving_board_pin(design: Design, part_id: str, pin: str) -> str | None:
    """Board GPIO pin (like 'D13') reached from part_id:pin, crossing resistors. None if none."""
    nets = _Nets(design)
    n = nets.net(f"{part_id}:{pin}")
    if n is None:
        return None
    for reach in nets.through_resistors(n):
        for bp in sorted(nets.board_pins(reach)):
            if bp.startswith("D") and bp[1:].isdigit():
                return bp
    return None


def run_electrical(design: Design, cat: Catalogue) -> RungResult:
    nets = _Nets(design)
    problems: list[str] = []
    problems += _rails_shorted(nets)
    problems += _leds_without_resistor(design, nets)
    problems += _wrong_supply(design, nets)
    problems += _driven_from_input_only(design, nets)
    total_ma, over = _current_budget(design)
    problems += over

    if problems:
        return RungResult(
            rung=Rung.ELECTRICAL,
            passed=False,
            summary=f"{len(problems)} electrical problem(s)",
            detail="\n".join(problems),
            extra={"estimated_ma": total_ma, "problems": problems},
        )
    return RungResult(
        rung=Rung.ELECTRICAL,
        passed=True,
        summary=f"about {total_ma} mA from USB, rails, resistors and supplies look right",
        extra={"estimated_ma": total_ma},
    )
