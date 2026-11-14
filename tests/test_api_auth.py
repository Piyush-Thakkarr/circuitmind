"""POST /generate with sign-in switched on: refused prompts stay free, no token is 401, over cap is 429.

The endpoint functions are called directly so the tests need no HTTP client.
"""

import pytest
from fastapi import HTTPException

from circuitmind import api, auth


@pytest.fixture
def signed_in_mode(monkeypatch):
    monkeypatch.setenv("CIRCUITMIND_SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("CIRCUITMIND_SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "wok_test")


def test_out_of_scope_is_answered_before_sign_in(signed_in_mode):
    out = api.generate(api.GenerateRequest(prompt="build me a drone that follows me"), authorization=None)
    assert "refused" in out


def test_no_token_is_401_with_a_sentence(signed_in_mode):
    with pytest.raises(HTTPException) as e:
        api.generate(api.GenerateRequest(prompt="blink an LED and print BLINK"), authorization=None)
    assert e.value.status_code == 401
    assert e.value.detail.startswith("Sign in first")


def test_over_cap_is_429(signed_in_mode, monkeypatch):
    user = auth.User(id="u1", email="", anonymous=True, token="tok")
    monkeypatch.setattr(auth, "verify", lambda token: user)
    monkeypatch.setattr(auth, "runs_today", lambda u: auth.DAILY_RUN_CAP)
    with pytest.raises(HTTPException) as e:
        api.generate(api.GenerateRequest(prompt="blink an LED and print BLINK"), authorization="Bearer tok")
    assert e.value.status_code == 429
    assert "runs for today" in e.value.detail


def test_health_reports_auth_and_budget(signed_in_mode, monkeypatch):
    monkeypatch.setattr(auth, "sim_ms_used_this_month", lambda token: 120_000)
    h = api.health()
    assert h["auth"] is True
    assert h["runs_per_day"] == auth.DAILY_RUN_CAP
    assert h["budget"]["used_ms"] == 120_000
    assert h["budget"]["total_ms"] == auth.MONTH_BUDGET_MS
