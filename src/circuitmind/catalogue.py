"""Load the part catalogue snapshot and answer questions about it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "catalogue" / "parts.json"

# ESP32 DevKit v1: pins that cannot drive output.
INPUT_ONLY_BOARD_PINS = {"D34", "D35", "VN", "VP"}


@dataclass(frozen=True)
class Catalogue:
    hash: str
    parts: dict[str, dict]

    def has(self, part_type: str) -> bool:
        return part_type in self.parts

    def pins(self, part_type: str) -> list[str]:
        return list(self.parts[part_type]["pins"])

    def describe(self, part_type: str) -> str:
        return self.parts[part_type]["description"]

    def board_gpio(self, pin: str) -> int | None:
        """Map a board pin name like 'D2' to GPIO 2. None if not a GPIO pin."""
        if pin.startswith("D") and pin[1:].isdigit():
            return int(pin[1:])
        return None

    def prompt_block(self) -> str:
        """Compact catalogue text for inclusion in a model prompt."""
        lines = []
        for t in sorted(self.parts):
            p = self.parts[t]
            lines.append(f"{t}: pins {', '.join(p['pins'])}. {p['description']}")
        return "\n".join(lines)


@lru_cache(maxsize=4)
def load(path: Path = DEFAULT_PATH) -> Catalogue:
    data = json.loads(Path(path).read_text())
    return Catalogue(hash=data["hash"], parts=data["parts"])
