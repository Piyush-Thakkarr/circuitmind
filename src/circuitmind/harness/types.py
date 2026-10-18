"""Shared types for the validation ladder."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Rung(str, Enum):
    SCHEMA = "schema"
    LINT = "lint"
    COMPILE = "compile"
    CONSISTENCY = "consistency"
    SIMULATE = "simulate"


@dataclass
class RungResult:
    rung: Rung
    passed: bool
    summary: str = ""
    detail: str = ""
    seconds: float = 0.0
    extra: dict = field(default_factory=dict)

    def feedback(self) -> str:
        """Short text suitable for sending back to the model."""
        head = f"[{self.rung.value}] {'passed' if self.passed else 'FAILED'}"
        if self.passed:
            return head
        return f"{head}: {self.summary}\n{self.detail}".rstrip()
