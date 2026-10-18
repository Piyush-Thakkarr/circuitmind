"""Rung 4b: wokwi-cli lint.

Findings are printed to stderr, one per line, prefixed with a glyph and a
bracketed rule id. The summary line goes to stdout. Exit code 1 on errors.
"""

from __future__ import annotations

import re
import subprocess
import time
from pathlib import Path

from .types import Rung, RungResult

_FINDING_RE = re.compile(r"^([✗⚠ℹ])\s+\[([a-z-]+)\]\s+(.*)$")

# Info-level rules that are noise for our purposes.
_IGNORE_RULES = {"unsupported-part"}


def run_lint(project_dir: Path, *, timeout: int = 60) -> RungResult:
    t0 = time.time()
    r = subprocess.run(
        ["wokwi-cli", "lint", str(project_dir)],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    errors: list[str] = []
    warnings: list[str] = []
    for line in (r.stdout + r.stderr).splitlines():
        m = _FINDING_RE.match(line.strip())
        if not m:
            continue
        glyph, rule, msg = m.groups()
        if rule in _IGNORE_RULES:
            continue
        if glyph == "✗":
            errors.append(f"{rule}: {msg}")
        elif glyph == "⚠":
            warnings.append(f"{rule}: {msg}")

    passed = r.returncode == 0 and not errors
    return RungResult(
        rung=Rung.LINT,
        passed=passed,
        summary=f"{len(errors)} error(s), {len(warnings)} warning(s)",
        detail="\n".join(errors + [f"warning {w}" for w in warnings]),
        seconds=time.time() - t0,
        extra={"errors": errors, "warnings": warnings, "returncode": r.returncode},
    )
