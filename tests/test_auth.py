"""Sign-in checks, the daily cap and the budget guard, with Supabase replaced by a fake."""

import pytest

from circuitmind import auth
from circuitmind.api import _bearer


@pytest.fixture
def supabase(monkeypatch):
    """Pretend Supabase is configured and answer requests from a dict of canned replies."""
    monkeypatch.setenv("CIRCUITMIND_SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("CIRCUITMIND_SUPABASE_ANON_KEY", "anon")
    calls = []
    replies = {}

    def fake_request(method, path, token, body=None, extra=None):
        calls.append((method, path, token, body))
        key = (method, path.split("?")[0])
        reply = replies.get(key)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(auth, "_request", fake_request)
    return {"calls": calls, "replies": replies}


USER = auth.User(id="u1", email="a@b.c", anonymous=False, token="tok")


def test_disabled_without_env(monkeypatch):
    monkeypatch.delenv("CIRCUITMIND_SUPABASE_URL", raising=False)
    monkeypatch.delenv("CIRCUITMIND_SUPABASE_ANON_KEY", raising=False)
    assert not auth.enabled()
    assert auth.budget_status() is None


def test_missing_token_is_a_plain_sentence(supabase):
    with pytest.raises(auth.AuthError, match="Sign in first"):
        auth.verify(None)


def test_bad_token_asks_to_sign_in_again(supabase):
    supabase["replies"][("GET", "/auth/v1/user")] = auth.AuthError("401: invalid JWT")
    with pytest.raises(auth.AuthError, match="Sign in again"):
        auth.verify("bad")


def test_verify_returns_the_user(supabase):
    supabase["replies"][("GET", "/auth/v1/user")] = {"id": "u1", "email": "a@b.c", "is_anonymous": False}
    u = auth.verify("tok")
    assert u == USER


def test_daily_cap_blocks_the_sixth_run(supabase):
    supabase["replies"][("GET", "/rest/v1/designs")] = [{"id": i} for i in range(5)]
    with pytest.raises(auth.AuthError, match="5 runs for today"):
        auth.check_allowed(USER, simulate=False, attempts=3, timeout_ms=8000)


def test_under_the_cap_and_budget_is_allowed(supabase):
    supabase["replies"][("GET", "/rest/v1/designs")] = [{"id": 1}]
    supabase["replies"][("POST", "/rest/v1/rpc/sim_ms_used_this_month")] = 60_000
    auth.check_allowed(USER, simulate=True, attempts=3, timeout_ms=8000)


def test_budget_guard_keeps_the_last_tenth(supabase):
    supabase["replies"][("GET", "/rest/v1/designs")] = []
    used = int(auth.MONTH_BUDGET_MS * 0.9) - 10_000  # three attempts of 8 s would cross the line
    supabase["replies"][("POST", "/rest/v1/rpc/sim_ms_used_this_month")] = used
    with pytest.raises(auth.AuthError, match="nearly gone"):
        auth.check_allowed(USER, simulate=True, attempts=3, timeout_ms=8000)
    # the same run without the simulator is fine
    auth.check_allowed(USER, simulate=False, attempts=3, timeout_ms=8000)


def test_record_and_update_go_through_as_the_user(supabase):
    supabase["replies"][("POST", "/rest/v1/designs")] = [{"id": "d1"}]
    supabase["replies"][("PATCH", "/rest/v1/designs")] = None
    assert auth.record_design(USER, {"prompt": "p", "status": "running"}) == "d1"
    assert auth.update_design(USER, "d1", {"status": "verified"})
    methods = [(m, p.split("?")[0], t) for m, p, t, _ in supabase["calls"]]
    assert methods == [("POST", "/rest/v1/designs", "tok"), ("PATCH", "/rest/v1/designs", "tok")]
    assert supabase["calls"][0][3]["user_id"] == "u1"


def test_bearer_header_parsing():
    assert _bearer("Bearer abc") == "abc"
    assert _bearer("bearer abc") == "abc"
    assert _bearer("Basic abc") is None
    assert _bearer(None) is None
    assert _bearer("Bearer ") is None
