"""Rung 4c: compile with arduino-cli.

Fixed FQBN, no build scripts, per-job build path. Produces the .bin and .elf
that wokwi-cli consumes.

The ESP32 core runs esptool three times per build (bootloader image, app
image, merged image). The esptool the core ships is a one-file bundle that
unpacks itself on every start, about 6.5 s each on this Mac, so those three
runs were 21 of a 25 s compile. When an esptool from pip is on the PATH (or
named in CIRCUITMIND_ESPTOOL) the core is told to use it instead; it starts in
under a second and the compile drops to about 11 s. Same esptool version, same
arguments, same output.

arduino-cli sometimes loses a file inside its own build folder part way through
a build ("opening dependency file .../build/sketch/sketch.ino.cpp.d: No such
file or directory"). It is rare, it is not caused by the sketch, and the same
build passes when run again. That one case gets a single retry with a clean
build folder; every other failure is reported as is.
"""

from __future__ import annotations

import os
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


def fast_esptool() -> Path | None:
    """An esptool that is not the core's slow one-file bundle, or None.

    CIRCUITMIND_ESPTOOL names it outright; otherwise the first ``esptool`` on
    the PATH is used unless it lives inside the Arduino packages folder.
    """
    named = os.environ.get("CIRCUITMIND_ESPTOOL")
    if named:
        p = Path(named)
        return p if p.is_file() else None
    found = shutil.which("esptool")
    if not found or "Arduino15" in found or ".arduino15" in found:
        return None
    return Path(found)


def compile_command(fqbn: str, sketch_dir: Path, build_dir: Path, esptool: Path | None) -> list[str]:
    cmd = [
        "arduino-cli",
        "compile",
        "--fqbn",
        fqbn,
        "--build-path",
        str(build_dir),
        "--warnings",
        "none",
    ]
    if esptool is not None:
        cmd += [
            "--build-property",
            f"tools.esptool_py.path={esptool.parent}",
            "--build-property",
            f"tools.esptool_py.cmd={esptool.name}",
        ]
    cmd.append(str(sketch_dir))
    return cmd


def _invoke(fqbn: str, sketch_dir: Path, build_dir: Path, timeout: int) -> subprocess.CompletedProcess:
    return subprocess.run(
        compile_command(fqbn, sketch_dir, build_dir, fast_esptool()),
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
            rung=Rung.COMPILE, passed=True, summary=size_line, seconds=secs,
            extra={"retried": retried, "fast_esptool": fast_esptool() is not None},
        ),
        bins,
    )
