"""The simulate rung must report a stalled simulator as a failed rung, never crash."""

import subprocess

from circuitmind.harness import simulate


def test_hung_simulator_is_a_failed_rung(tmp_path, monkeypatch):
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "test")
    (tmp_path / "serial.log").write_text("boot\nold line\n")

    def fake_run(cmd, **kwargs):
        # Pretend wokwi-cli wrote a little, then never returned.
        (tmp_path / "serial.log").write_text("boot\nI2C init\n")
        raise subprocess.TimeoutExpired(cmd, kwargs.get("timeout", 0))

    monkeypatch.setattr(subprocess, "run", fake_run)
    scenario = tmp_path / "scenario.yaml"
    scenario.write_text("steps: []\n")

    r = simulate.run_simulate(tmp_path, scenario, timeout_ms=5000)

    assert r.passed is False
    assert r.extra["returncode"] == simulate.HUNG_EXIT
    assert "did not return" in r.summary
    assert "I2C init" in r.detail
    assert "old line" not in r.detail  # previous run's log was cleared first
    assert r.extra["flake_retry"] is False  # a hang is not retried


def test_missing_token_fails_without_running(tmp_path, monkeypatch):
    monkeypatch.delenv("WOKWI_CLI_TOKEN", raising=False)
    r = simulate.run_simulate(tmp_path, tmp_path / "scenario.yaml", timeout_ms=1000)
    assert r.passed is False
    assert "WOKWI_CLI_TOKEN" in r.summary
