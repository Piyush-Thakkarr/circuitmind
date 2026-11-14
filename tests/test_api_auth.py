"""POST /generate with sign-in switched on: refused prompts stay free, no token is 401, over cap is 429."""

import pytest
from fastapi.testclient import TestClient

from circuitmind import api, auth


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("CIRCUITMIND_SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("CIRCUITMIND_SUPABASE_ANON_KEY", "anon")
    monkeypatch.setenv("WOKWI_CLI_TOKEN", "wok_test")
    return TestClient(api.app)


def test_out_of_scope_is_answered_before_sign_in(client):
    r = client.post("/generate", json={"prompt": "build me a drone that follows me"})
    assert r.status_code == 200
    assert "refused" in r.json()


def test_no_token_is_401_with_a_sentence(client):
    r = client.post("/generate", json={"prompt": "blink an LED and print BLINK"})
    assert r.status_code == 401
    assert r.json()["detail"].startswith("Sign in first")


def test_over_cap_is_429(client, monkeypatch):
    user = auth.User(id="u1", email="", anonymous=True, token="tok")
    monkeypatch.setattr(auth, "verify", lambda token: user)
    monkeypatch.setattr(auth, "runs_today", lambda u: auth.DAILY_RUN_CAP)
    r = client.post("/generate", json={"prompt": "blink an LED and print BLINK"},
                    headers={"Authorization": "Bearer tok"})
    assert r.status_code == 429
    assert "runs for today" in r.json()["detail"]


def test_health_reports_auth_and_budget(client, monkeypatch):
    monkeypatch.setattr(auth, "sim_ms_used_this_month", lambda token: 120_000)
    h = client.get("/health").json()
    assert h["auth"] is True
    assert h["runs_per_day"] == auth.DAILY_RUN_CAP
    assert h["budget"]["used_ms"] == 120_000
    assert h["budget"]["total_ms"] == auth.MONTH_BUDGET_MS
