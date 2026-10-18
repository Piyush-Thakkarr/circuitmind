"""Rung 5: simulate with wokwi-cli.

Verdict is the exit code. 0 pass, 42 timeout, anything else failure. The
serial log is captured for feedback and humans, never for the verdict.
One automatic retry on timeout, flagged as a possible flake.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from .types import Rung, RungResult

TIMEOUT_EXIT = 42
_SERIAL_TAIL_LINES = 20


def write_wokwi_toml(project_dir: Path, bin_path: Path, elf_path: Path) -> Path:
    toml = project_dir / "wokwi.toml"
    toml.write_text(
        "[wokwi]\nversion = 1\n"
        f'firmware = "{os.path.relpath(bin_path, project_dir)}"\n'
        f'elf = "{os.path.relpath(elf_path, project_dir)}"\n'
    )
    return toml


def _once(project_dir: Path, scenario: Path, timeout_ms: int) -> tuple[int, str, float]:
    log = project_dir / "serial.log"
    t0 = time.time()
    r = subprocess.run(
        [
            "wokwi-cli",
            str(project_dir),
            "--scenario",
            str(scenario.relative_to(project_dir)) if scenario.is_relative_to(project_dir) else str(scenario),
            "--timeout",
            str(timeout_ms),
            "--timeout-exit-code",
            str(TIMEOUT_EXIT),
            "--serial-log-file",
            str(log),
            "--quiet",
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_ms / 1000 + 120,
        env={**os.environ},
    )
    serial = log.read_text(errors="replace") if log.exists() else ""
    combined = serial or (r.stdout + r.stderr)
    return r.returncode, combined, time.time() - t0


def run_simulate(
    project_dir: Path, scenario: Path, timeout_ms: int, *, retry_on_timeout: bool = True
) -> RungResult:
    if not os.environ.get("WOKWI_CLI_TOKEN"):
        return RungResult(
            rung=Rung.SIMULATE,
            passed=False,
            summary="WOKWI_CLI_TOKEN not set",
            detail="simulation requires a token from https://wokwi.com/dashboard/ci",
        )

    rc, serial, secs = _once(project_dir, scenario, timeout_ms)
    flake = False
    if rc == TIMEOUT_EXIT and retry_on_timeout:
        rc2, serial2, secs2 = _once(project_dir, scenario, timeout_ms)
        if rc2 != TIMEOUT_EXIT:
            flake = True
        rc, serial, secs = rc2, serial2, secs + secs2

    tail = "\n".join(serial.strip().splitlines()[-_SERIAL_TAIL_LINES:])
    passed = rc == 0
    if passed:
        summary = "scenario passed"
    elif rc == TIMEOUT_EXIT:
        summary = f"timed out after {timeout_ms} ms without the expected serial output"
    else:
        summary = f"simulation failed (exit {rc})"
    return RungResult(
        rung=Rung.SIMULATE,
        passed=passed,
        summary=summary,
        detail=f"last serial lines:\n{tail}" if tail else "no serial output captured",
        seconds=secs,
        extra={
            "returncode": rc,
            "flake_retry": flake,
            "sim_ms_charged": timeout_ms * (2 if flake or (rc == TIMEOUT_EXIT and retry_on_timeout) else 1),
        },
    )
