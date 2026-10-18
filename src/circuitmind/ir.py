"""Intermediate representation of a circuit design.

The model produces this, not a full Wokwi diagram. Everything cosmetic
(positions, wire colours, routing) is filled in by ``expand``.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

BOARD_ID = "esp"
"""Fixed id for the microcontroller part. Connections reference it as ``esp:<pin>``."""

_ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
_REF_RE = re.compile(r"^([a-z][a-z0-9_]{0,31}):([A-Za-z0-9_.+\-/]+)$")


class Part(BaseModel):
    id: str
    type: str
    attrs: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def _id_ok(cls, v: str) -> str:
        if not _ID_RE.match(v):
            raise ValueError(f"part id {v!r} must be lowercase alphanumeric, start with a letter")
        if v == BOARD_ID:
            raise ValueError(f"part id {BOARD_ID!r} is reserved for the board")
        return v

    @field_validator("attrs")
    @classmethod
    def _attrs_str(cls, v: dict[str, Any]) -> dict[str, str]:
        return {k: str(val) for k, val in v.items()}


class Design(BaseModel):
    board: str
    parts: list[Part]
    connections: list[tuple[str, str]]
    firmware: str
    status_line: str
    explanation: str = ""

    @field_validator("connections")
    @classmethod
    def _conn_format(cls, v: list[tuple[str, str]]) -> list[tuple[str, str]]:
        for a, b in v:
            for ref in (a, b):
                if not _REF_RE.match(ref):
                    raise ValueError(f"connection endpoint {ref!r} must look like partid:PIN")
        return v

    @field_validator("status_line")
    @classmethod
    def _status_line(cls, v: str) -> str:
        v = v.strip()
        if not v or "\n" in v:
            raise ValueError("status_line must be a single non-empty line")
        return v

    @model_validator(mode="after")
    def _cross_checks(self) -> Design:
        ids = [p.id for p in self.parts]
        dupes = {i for i in ids if ids.count(i) > 1}
        if dupes:
            raise ValueError(f"duplicate part ids: {sorted(dupes)}")
        known = set(ids) | {BOARD_ID}
        for a, b in self.connections:
            for ref in (a, b):
                pid = ref.split(":", 1)[0]
                if pid not in known:
                    raise ValueError(f"connection references unknown part {pid!r}")
        if self.status_line not in self.firmware:
            raise ValueError(
                f"firmware must print the status line {self.status_line!r} verbatim"
            )
        return self

    def part_ids(self) -> set[str]:
        return {p.id for p in self.parts}

    def board_pins_used(self) -> set[str]:
        """Board pin names referenced by any connection, e.g. {'D2', 'GND.1'}."""
        pins: set[str] = set()
        for a, b in self.connections:
            for ref in (a, b):
                pid, pin = ref.split(":", 1)
                if pid == BOARD_ID:
                    pins.add(pin)
        return pins


def design_json_schema() -> dict[str, Any]:
    """JSON schema to hand to a model provider's structured-output mechanism."""
    return Design.model_json_schema()
