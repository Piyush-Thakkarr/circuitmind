"""Rung 4d: firmware pins versus wiring.

Blocks only when it is certain: a GPIO number appears in a pin call AND no
wired board pin maps to that GPIO. Anything the check cannot resolve is passed
through and reported as such.

What it can resolve, without running the code:
- numbers, `#define NAME 4`, `const int NAME = 4` (also comma-separated lists)
- arrays of pins, `byte rows[4] = {13, 12, 14, 27}`; `rows[i]` means all of them
- a helper's parameter, `void press(int pin)`, when every call site passes a
  number or a known name; the parameter then means the set of those values
"""

from __future__ import annotations

import re

from ..catalogue import INPUT_ONLY_BOARD_PINS, Catalogue
from ..ir import Design
from .types import Rung, RungResult

_PIN_CALLS = (
    "pinMode|digitalWrite|digitalRead|analogRead|analogWrite|ledcAttachPin|ledcAttach|"
    "tone|noTone|pulseIn|attach"
)
_CALL_RE = re.compile(rf"\b({_PIN_CALLS})\s*\(\s*([^,()]*?)\s*(,|\))")
_SIMPLE_ARG_RE = re.compile(r"[A-Za-z_]\w*(?:\s*\[[^\]]*\])?|\d+")
_DEFINE_RE = re.compile(r"#define\s+([A-Za-z_]\w*)\s+(\d+)\b")
_DECL_RE = re.compile(r"\b(?:const\s+)?(?:int|uint8_t|byte|unsigned\s+int)\s+([^;{}\[\]]*);")
_ASSIGN_RE = re.compile(r"([A-Za-z_]\w*)\s*=\s*(\d+)")
_ARRAY_RE = re.compile(
    r"\b(?:const\s+)?(?:int|uint8_t|byte|unsigned\s+int)\s+([A-Za-z_]\w*)\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}"
)
_FUNC_DEF_RE = re.compile(
    r"\b(?:void|int|bool|long|float|double|unsigned\s+long|uint8_t|byte)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*\{"
)
# calls that drive a pin; pinMode is added when its mode argument says OUTPUT
_DRIVING_CALLS = {"digitalWrite", "analogWrite", "ledcAttachPin", "ledcAttach", "tone", "attach"}


def _matching(src: str, start: int, open_ch: str, close_ch: str) -> int:
    """Index just past the bracket that closes the one at `start`; len(src) if unbalanced."""
    depth = 0
    for i in range(start, len(src)):
        if src[i] == open_ch:
            depth += 1
        elif src[i] == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
    return len(src)


def _split_args(text: str) -> list[str]:
    out, depth, cur = [], 0, []
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        if ch == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(ch)
    if cur or out:
        out.append("".join(cur).strip())
    return out


class _Resolver:
    def __init__(self, firmware: str) -> None:
        self.src = firmware
        self.names: dict[str, int] = {}
        for m in _DEFINE_RE.finditer(firmware):
            self.names[m.group(1)] = int(m.group(2))
        for m in _DECL_RE.finditer(firmware):
            for a in _ASSIGN_RE.finditer(m.group(1)):
                self.names[a.group(1)] = int(a.group(2))
        self.names.setdefault("LED_BUILTIN", 2)

        self.arrays: dict[str, set[int] | None] = {}
        for m in _ARRAY_RE.finditer(firmware):
            vals = [self._value(e) for e in _split_args(m.group(2)) if e]
            self.arrays[m.group(1)] = None if any(v is None for v in vals) else {v for v in vals if v is not None}

        # functions: name -> (param names, body start, body end)
        self.funcs: dict[str, tuple[list[str], int, int]] = {}
        for m in _FUNC_DEF_RE.finditer(firmware):
            params = []
            for p in _split_args(m.group(2)):
                tokens = p.replace("&", " ").replace("*", " ").split()
                if tokens:
                    params.append(tokens[-1])
            body_start = m.end() - 1
            self.funcs[m.group(1)] = (params, body_start, _matching(firmware, body_start, "{", "}"))

        # parameter values from call sites: (function, index) -> set or None
        self.param_values: dict[tuple[str, int], set[int] | None] = {}
        for fname, (params, b0, b1) in self.funcs.items():
            if fname in ("setup", "loop") or not params:
                continue
            values: list[set[int] | None] = [set() for _ in params]
            for cm in re.finditer(rf"\b{re.escape(fname)}\s*\(", firmware):
                if b0 >= cm.start() >= self._def_start(fname):
                    continue  # the definition itself
                end = _matching(firmware, cm.end() - 1, "(", ")")
                args = _split_args(firmware[cm.end():end - 1])
                for i, arg in enumerate(args[: len(params)]):
                    v = self._value(arg)
                    if v is None or values[i] is None:
                        values[i] = None
                    else:
                        values[i].add(v)
            for i, p in enumerate(params):
                self.param_values[(fname, i)] = values[i]

    def _def_start(self, fname: str) -> int:
        m = re.search(rf"\b{re.escape(fname)}\s*\([^)]*\)\s*\{{", self.src)
        return m.start() if m else -1

    def _value(self, text: str) -> int | None:
        text = text.strip()
        if text.isdigit():
            return int(text)
        return self.names.get(text)

    def _enclosing(self, pos: int) -> str | None:
        for fname, (_, b0, b1) in self.funcs.items():
            if b0 <= pos < b1:
                return fname
        return None

    def gpio_literals(self) -> tuple[set[int], set[int], bool]:
        """Return (gpio used, gpio driven as output, fully resolved)."""
        used: set[int] = set()
        driven: set[int] = set()
        resolved = True
        for m in _CALL_RE.finditer(self.src):
            call, arg = m.group(1), m.group(2).strip()
            vals = self._arg_values(arg, m.start())
            if vals is None:
                resolved = False
                continue
            used |= vals
            if call in _DRIVING_CALLS or (call == "pinMode" and self._mode_is_output(m.end())):
                driven |= vals
        return used, driven, resolved

    def _mode_is_output(self, pos: int) -> bool:
        rest = self.src[pos:pos + 40]
        return bool(re.match(r"\s*OUTPUT\b", rest))

    def _arg_values(self, arg: str, pos: int) -> set[int] | None:
        if not _SIMPLE_ARG_RE.fullmatch(arg):
            return None  # an expression, a member access, a cast: not ours to guess
        if arg.isdigit():
            return {int(arg)}
        if "[" in arg:
            name = arg.split("[", 1)[0].strip()
            return self.arrays.get(name)
        if arg in self.names:
            return {self.names[arg]}
        fname = self._enclosing(pos)
        if fname and fname in self.funcs:
            params = self.funcs[fname][0]
            if arg in params:
                return self.param_values.get((fname, params.index(arg)))
        return None


def _gpio_literals(firmware: str) -> tuple[set[int], bool]:
    """Kept for callers that only want (used, resolved)."""
    used, _, resolved = _Resolver(firmware).gpio_literals()
    return used, resolved


def run_consistency(design: Design, cat: Catalogue) -> RungResult:
    used, driven, resolved = _Resolver(design.firmware).gpio_literals()
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
        and (g := cat.board_gpio(p)) is not None and g in driven
    )
    if outputs_on_input_only:
        problems.append(f"pins {outputs_on_input_only} are input-only on the ESP32 and cannot drive output")

    extra = {"used_gpio": sorted(used), "wired_gpio": sorted(wired_gpio), "resolved": resolved}
    if problems:
        return RungResult(
            rung=Rung.CONSISTENCY,
            passed=False,
            summary="firmware and wiring disagree",
            detail="\n".join(problems),
            extra=extra,
        )
    note = "" if resolved else "some pin arguments could not be resolved statically; passed through"
    return RungResult(rung=Rung.CONSISTENCY, passed=True, summary=note, extra=extra)
