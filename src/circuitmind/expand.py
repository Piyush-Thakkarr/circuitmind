"""Expand a Design into a complete Wokwi diagram.json.

Layout is deterministic: board at the origin, other parts on a grid to its
right, column-major. Wire colours follow a fixed rule. Routing arrays are
empty so the simulator auto-routes.
"""

from __future__ import annotations

import json
from typing import Any

from .ir import BOARD_ID, Design

GRID_X0 = 260
GRID_DX = 150
GRID_DY = 120
GRID_ROWS = 4

_POWER_PINS = {"VCC", "VDD", "V+", "5V", "3V3", "3.3V", "VIN"}
_GROUND_PINS = {"GND", "VSS", "K", "GND.1", "GND.2", "GND.3"}


def _wire_colour(a: str, b: str) -> str:
    pa = a.split(":", 1)[1]
    pb = b.split(":", 1)[1]
    if pa in _GROUND_PINS or pb in _GROUND_PINS:
        return "black"
    if pa in _POWER_PINS or pb in _POWER_PINS:
        return "red"
    return "green"


def expand(design: Design, *, inject_serial_monitor: bool = False) -> dict[str, Any]:
    """Return a diagram.json dict.

    ``inject_serial_monitor`` adds the two ``$serialMonitor`` connections.
    Whether the ESP32 DevKit v1 needs them is an open question; the harness
    tests both and the caller passes the answer.
    """
    parts: list[dict[str, Any]] = [
        {"type": design.board, "id": BOARD_ID, "top": 0, "left": 0, "attrs": {}}
    ]
    for i, p in enumerate(design.parts):
        col, row = divmod(i, GRID_ROWS)
        parts.append(
            {
                "type": p.type,
                "id": p.id,
                "top": row * GRID_DY,
                "left": GRID_X0 + col * GRID_DX,
                "attrs": dict(p.attrs),
            }
        )

    connections: list[list[Any]] = [[a, b, _wire_colour(a, b), []] for a, b in design.connections]

    if inject_serial_monitor:
        connections.insert(0, [f"{BOARD_ID}:TX0", "$serialMonitor:RX", "", []])
        connections.insert(1, [f"{BOARD_ID}:RX0", "$serialMonitor:TX", "", []])

    return {
        "version": 1,
        "author": "circuitmind",
        "editor": "wokwi",
        "parts": parts,
        "connections": connections,
    }


def canonical_json(diagram: dict[str, Any]) -> str:
    """Stable serialisation for hashing and cache keys."""
    return json.dumps(diagram, sort_keys=True, separators=(",", ":"))
