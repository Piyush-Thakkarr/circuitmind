"""Every test gets its own Wokwi quota state file.

The simulate rung writes runs/wokwi_quota.json on every run, and the API and
bench read it. Without this, a test run would overwrite what the real
simulator last said on this machine, and tests would read the machine's state.
"""

import pytest


@pytest.fixture(autouse=True)
def own_quota_state_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRCUITMIND_QUOTA_FILE", str(tmp_path / "wokwi_quota.json"))
