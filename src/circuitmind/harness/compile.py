"""Rung 4c: compile with arduino-cli.

Fixed FQBN, no build scripts, per-job build path. Produces the .bin and .elf
that wokwi-cli consumes.

arduino-cli sometimes loses a file inside its own build folder part way through
a build ("opening dependency file .../build/sketch/sketch.ino.cpp.d: No such
file or directory"). It is rare, it is not caused by the sketch, and the same
build passes when run again. That one case gets a single retry with a clean
build folder; every other failure is reported as is.
"""

from __future__ import annotations

import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .types import Rung, RungResult

FQBN = {
    "wokwi-esp32-devkit-v1": "esp32:esp32:esp32doit-devkit-v1",
}

_MAX_ERROR_LINES = 12


@dataclass
class Binaries:
    bin: Path
    elf: Path


def _error_excerpt(stderr: str) -> str:
    lines = [ln for ln in stderr.splitlines() if "error" in ln.lower() or "undefined" in ln.lower()]
    if not lines:
        lines = stderr.strip().splitlines()[-_MAX_ERROR_LINES:]
    return "\n".join(lines[:_MAX_ERROR_LINES])


def _lost_build_file(output: str, build_dir: Path) -> bool:
    """True when arduino-cli complains that a file inside build_dir is missing."""
    needle = str(build_dir).lower()
    for line in output.lower().splitlines():
        if "no such file or directory" in line and needle in line:
            return True
    return False


def _invoke(fqbn: str, sketch_dir: Path, build_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            "arduino-cli",
            "compile",
            "--fqbn",
            fqbn,
            "--export-binaries",
            "--build-path",
            str(build_dir),
            "--warnings",
            "none",
            str(sketch_dir),
        ],
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )


def run_compile(
    sketch_dir: Path, board_type: str, *, build_dir: Path, timeout: int = 300
) -> tuple[RungResult, Binaries | None]:
    """sketch_dir must contain exactly one .ino named after the directory."""
    fqbn = FQBN[board_type]
    build_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    r = _invoke(fqbn, sketch_dir, build_dir, timeout)
    retried = False
    if r.returncode != 0 and _lost_build_file(r.stderr or r.stdout, build_dir):
        shutil.rmtree(build_dir, ignore_errors=True)
        build_dir.mkdir(parents=True, exist_ok=True)
        r = _invoke(fqbn, sketch_dir, build_dir, timeout)
        retried = True
    secs = time.time() - t0
    if r.returncode != 0:
        return (
            RungResult(
                rung=Rung.COMPILE,
                passed=False,
                summary="compilation failed",
                detail=_error_excerpt(r.stderr or r.stdout),
                seconds=secs,
                extra={"returncode": r.returncode, "retried": retried},
            ),
            None,
        )
    name = sketch_dir.name
    bins = Binaries(bin=build_dir / f"{name}.ino.bin", elf=build_dir / f"{name}.ino.elf")
    if not bins.bin.exists() or not bins.elf.exists():
        return (
            RungResult(
                rung=Rung.COMPILE,
                passed=False,
                summary="compiled but binaries not found",
                detail=f"expected {bins.bin} and {bins.elf}",
                seconds=secs,
            ),
            None,
        )
    size_line = next((ln for ln in r.stdout.splitlines() if "Sketch uses" in ln), "").strip()
    if retried:
        size_line += " (second try: arduino-cli lost a file in its build folder on the first)"
    return (
        RungResult(
            rung=Rung.COMPILE, passed=True, summary=size_line, seconds=secs, extra={"retried": retried}
        ),
        bins,
    )
