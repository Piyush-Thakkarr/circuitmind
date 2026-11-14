"""The compile rung retries once, and only when arduino-cli lost a file in its own build folder."""

import subprocess
from pathlib import Path

from circuitmind.harness import compile as compile_mod


def _fake_runs(replies, build_dir: Path):
    """Return a subprocess.run stand-in that plays `replies` in order.

    Each reply is (returncode, stdout, stderr). A zero return code also drops the
    .bin and .elf the rung looks for.
    """
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        rc, out, err = replies[len(calls) - 1]
        if rc == 0:
            (build_dir / "sketch.ino.bin").write_bytes(b"x")
            (build_dir / "sketch.ino.elf").write_bytes(b"x")
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr=err)

    return fake_run, calls


def test_lost_build_file_is_retried_once(tmp_path, monkeypatch):
    sketch = tmp_path / "sketch"
    sketch.mkdir()
    build = tmp_path / "build"
    lost = (
        f"{sketch}/sketch.ino:25:1: fatal error: opening dependency file "
        f"{build}/sketch/sketch.ino.cpp.d: No such file or directory\nError during build: exit status 1"
    )
    fake, calls = _fake_runs([(1, "", lost), (0, "Sketch uses 1000 bytes (1%)", "")], build)
    monkeypatch.setattr(compile_mod.subprocess, "run", fake)

    result, bins = compile_mod.run_compile(sketch, "wokwi-esp32-devkit-v1", build_dir=build)

    assert result.passed
    assert bins is not None and bins.bin.exists()
    assert len(calls) == 2
    assert result.extra["retried"] is True
    assert "second try" in result.summary


def test_real_compile_error_is_not_retried(tmp_path, monkeypatch):
    sketch = tmp_path / "sketch"
    sketch.mkdir()
    build = tmp_path / "build"
    missing_header = f"{sketch}/sketch.ino:1:10: fatal error: ESP32Servo.h: No such file or directory"
    fake, calls = _fake_runs([(1, "", missing_header), (0, "unreachable", "")], build)
    monkeypatch.setattr(compile_mod.subprocess, "run", fake)

    result, bins = compile_mod.run_compile(sketch, "wokwi-esp32-devkit-v1", build_dir=build)

    assert not result.passed
    assert bins is None
    assert len(calls) == 1
    assert "ESP32Servo.h" in result.detail
    assert result.extra["retried"] is False


def test_second_failure_is_reported(tmp_path, monkeypatch):
    sketch = tmp_path / "sketch"
    sketch.mkdir()
    build = tmp_path / "build"
    lost = f"error: {build}/sketch/sketch.ino.cpp.merged: no such file or directory"
    fake, calls = _fake_runs([(1, "", lost), (1, "", lost)], build)
    monkeypatch.setattr(compile_mod.subprocess, "run", fake)

    result, _ = compile_mod.run_compile(sketch, "wokwi-esp32-devkit-v1", build_dir=build)

    assert not result.passed
    assert len(calls) == 2
    assert result.extra["retried"] is True


def test_fast_esptool_is_used_when_present(monkeypatch, tmp_path):
    from circuitmind.harness import compile as c

    tool = tmp_path / "esptool"
    tool.write_text("")
    monkeypatch.setenv("CIRCUITMIND_ESPTOOL", str(tool))
    assert c.fast_esptool() == tool
    cmd = c.compile_command("esp32:esp32:esp32doit-devkit-v1", tmp_path / "s", tmp_path / "b", tool)
    assert f"tools.esptool_py.path={tmp_path}" in cmd
    assert "tools.esptool_py.cmd=esptool" in cmd
    assert cmd[-1] == str(tmp_path / "s")


def test_the_cores_own_esptool_is_not_treated_as_fast(monkeypatch):
    from circuitmind.harness import compile as c

    monkeypatch.delenv("CIRCUITMIND_ESPTOOL", raising=False)
    monkeypatch.setattr(c.shutil, "which", lambda name: "/Users/x/Library/Arduino15/packages/esp32/tools/esptool_py/5.3.1/esptool")
    assert c.fast_esptool() is None
    monkeypatch.setattr(c.shutil, "which", lambda name: None)
    assert c.fast_esptool() is None
    cmd = c.compile_command("f", __import__("pathlib").Path("s"), __import__("pathlib").Path("b"), None)
    assert not any(a.startswith("tools.esptool_py") for a in cmd)
