"""Run a Design up the validation ladder.

Free rungs first, simulation last, stop at the first failure.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..catalogue import Catalogue
from ..expand import canonical_json, expand
from ..ir import Design
from ..scenario import adapt_to_design
from .compile import run_compile
from .consistency import run_consistency
from .electrical import run_electrical
from .lint import run_lint
from .simulate import run_simulate, write_wokwi_toml
from .types import Rung, RungResult


@dataclass
class LadderOutcome:
    results: list[RungResult] = field(default_factory=list)
    passed: bool = False
    diagram_json: str = ""

    @property
    def failed_rung(self) -> Rung | None:
        for r in self.results:
            if not r.passed:
                return r.rung
        return None

    def feedback(self) -> str:
        return "\n".join(r.feedback() for r in self.results)


_STATIC_ENTRY = re.compile(r"\bstatic\s+(?=void\s+(?:setup|loop)\s*\()")


def sanitize_firmware(src: str) -> str:
    """Repairs that are always safe and that models get wrong repeatedly.

    Arduino's build declares setup() and loop() for the core to call, so a
    ``static`` on either one fails to link. Stripping it never changes a
    correct sketch.
    """
    return _STATIC_ENTRY.sub("", src)


def _schema_rung(design: Design, cat: Catalogue) -> RungResult:
    unknown = sorted(p.type for p in design.parts if not cat.has(p.type))
    if not cat.has(design.board):
        unknown.append(design.board)
    if unknown:
        return RungResult(
            rung=Rung.SCHEMA,
            passed=False,
            summary="unknown part type(s)",
            detail="not in catalogue: " + ", ".join(unknown),
        )
    return RungResult(rung=Rung.SCHEMA, passed=True)


def run_ladder(
    design: Design,
    cat: Catalogue,
    workdir: Path,
    *,
    scenario: Path | None,
    timeout_ms: int,
    simulate: bool = True,
    inject_serial_monitor: bool = False,
    on_rung=None,
) -> LadderOutcome:
    out = LadderOutcome()
    workdir.mkdir(parents=True, exist_ok=True)
    notify = on_rung or (lambda r: None)

    r = _schema_rung(design, cat)
    out.results.append(r)
    notify(r)
    if not r.passed:
        return out

    diagram = expand(design, inject_serial_monitor=inject_serial_monitor)
    out.diagram_json = canonical_json(diagram)
    (workdir / "diagram.json").write_text(json.dumps(diagram, indent=2))

    r = run_lint(workdir)
    out.results.append(r)
    notify(r)
    if not r.passed:
        return out

    sketch_dir = workdir / "sketch"
    sketch_dir.mkdir(exist_ok=True)
    (sketch_dir / "sketch.ino").write_text(sanitize_firmware(design.firmware))
    r, bins = run_compile(sketch_dir, design.board, build_dir=workdir / "build")
    out.results.append(r)
    notify(r)
    if not r.passed or bins is None:
        return out

    r = run_consistency(design, cat)
    out.results.append(r)
    notify(r)
    if not r.passed:
        return out

    r = run_electrical(design, cat)
    out.results.append(r)
    notify(r)
    if not r.passed:
        return out

    if not simulate:
        out.passed = True
        return out

    if scenario is None:
        raise ValueError("scenario required when simulate=True")
    adapted, notes, missing = adapt_to_design(scenario.read_text(), design)
    if missing:
        r = RungResult(
            rung=Rung.SIMULATE,
            passed=False,
            summary="the design lacks a part the test drives",
            detail="\n".join(missing),
            extra={"scenario_missing": missing},
        )
        out.results.append(r)
        notify(r)
        return out
    scen_path = workdir / "scenario.adapted.yaml"
    scen_path.write_text(adapted)
    write_wokwi_toml(workdir, bins.bin, bins.elf)
    r = run_simulate(workdir, scen_path, timeout_ms)
    if notes:
        r.summary = (r.summary + "; " if r.summary else "") + "scenario parts mapped: " + ", ".join(notes)
        r.extra["scenario_notes"] = notes
    out.results.append(r)
    notify(r)
    out.passed = r.passed
    return out
