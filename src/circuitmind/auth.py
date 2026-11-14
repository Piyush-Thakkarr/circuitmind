"""Who is asking, how many runs they have had today, and how much simulation
budget is left this month. All of it goes through Supabase with the caller's
own token, so the engine holds no secret of its own.

Auth is on only when CIRCUITMIND_SUPABASE_URL and CIRCUITMIND_SUPABASE_ANON_KEY
are set. A developer running the engine on a laptop without them gets the old
open behaviour, with a warning in /health.

The caller's Supabase access token comes in the Authorization header. The
engine asks Supabase who it belongs to (GET /auth/v1/user). Runs are rows in
the ``designs`` table; row-level security means a user can only ever count or
read their own rows, and the engine inserts rows as that user. The month's
simulation total across everyone comes from the ``sim_ms_used_this_month``
function, which runs with the table owner's rights so it can sum every row.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

DAILY_RUN_CAP = int(os.environ.get("CIRCUITMIND_RUNS_PER_DAY", "5"))
MONTH_BUDGET_MS = int(os.environ.get("CIRCUITMIND_SIM_BUDGET_MS_PER_MONTH", "3000000"))
"""Wokwi free tier: 50 simulated minutes a month."""
BUDGET_STOP_AT = 0.9
"""Refuse new simulated runs once this share of the month's budget is spent."""
_TIMEOUT_S = 10


@dataclass(frozen=True)
class User:
    id: str
    email: str
    anonymous: bool
    token: str


class AuthError(Exception):
    """The request cannot go ahead; ``str(e)`` is a plain sentence for the user."""


def enabled() -> bool:
    return bool(os.environ.get("CIRCUITMIND_SUPABASE_URL") and os.environ.get("CIRCUITMIND_SUPABASE_ANON_KEY"))


def _base() -> str:
    return os.environ["CIRCUITMIND_SUPABASE_URL"].rstrip("/")


def _request(method: str, path: str, token: str, body: Any = None, extra: dict[str, str] | None = None) -> Any:
    data = json.dumps(body).encode() if body is not None else None
    headers = {
        "apikey": os.environ["CIRCUITMIND_SUPABASE_ANON_KEY"],
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        **(extra or {}),
    }
    req = urllib.request.Request(_base() + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_S) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            msg = json.loads(raw).get("msg") or json.loads(raw).get("message") or raw.decode(errors="replace")
        except (ValueError, AttributeError):
            msg = raw.decode(errors="replace")
        raise AuthError(f"{e.code}: {msg[:200]}") from None
    except (urllib.error.URLError, TimeoutError) as e:
        raise AuthError(f"could not reach the sign-in service: {e}") from None
    return json.loads(raw) if raw else None


def verify(token: str | None) -> User:
    """The user a Supabase access token belongs to. Raises AuthError when it is missing or bad."""
    if not token:
        raise AuthError("Sign in first. Runs are limited per person so the free simulation budget lasts the month.")
    try:
        u = _request("GET", "/auth/v1/user", token)
    except AuthError as e:
        if str(e).startswith("40"):
            raise AuthError("Your sign-in has expired or is not valid. Sign in again.") from None
        raise
    return User(id=u["id"], email=u.get("email") or "", anonymous=bool(u.get("is_anonymous")), token=token)


def runs_today(user: User) -> int:
    """How many designs this user has started since midnight UTC (their own rows only)."""
    start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    rows = _request(
        "GET", f"/rest/v1/designs?select=id&created_at=gte.{start}", user.token,
        extra={"Prefer": "count=exact"},
    )
    return len(rows or [])


def sim_ms_used_this_month(token: str) -> int:
    v = _request("POST", "/rest/v1/rpc/sim_ms_used_this_month", token, body={})
    return int(v or 0)


def check_allowed(user: User, *, simulate: bool, attempts: int, timeout_ms: int) -> None:
    """Raise AuthError if this run must not start: daily cap or monthly budget."""
    n = runs_today(user)
    if n >= DAILY_RUN_CAP:
        raise AuthError(
            f"You have used your {DAILY_RUN_CAP} runs for today. The free simulator budget is shared by "
            "everyone, so each person gets a few runs a day. Try again tomorrow."
        )
    if simulate:
        used = sim_ms_used_this_month(user.token)
        worst_case = attempts * timeout_ms
        if used + worst_case > MONTH_BUDGET_MS * BUDGET_STOP_AT:
            left_min = max(0, (MONTH_BUDGET_MS - used) // 60000)
            raise AuthError(
                f"The month's free simulation budget is nearly gone (about {left_min} simulated minutes left "
                "and the last tenth is kept in reserve). Untick 'run in simulator' to get a design that passed "
                "the free checks only, or come back next month."
            )


def record_design(user: User, row: dict[str, Any]) -> str | None:
    """Insert the run as this user. Returns the row id, or None if Supabase refused."""
    try:
        res = _request(
            "POST", "/rest/v1/designs", user.token,
            body={**row, "user_id": user.id},
            extra={"Prefer": "return=representation"},
        )
    except AuthError:
        return None
    if isinstance(res, list) and res:
        return res[0].get("id")
    return None


def update_design(user: User, design_id: str, row: dict[str, Any]) -> bool:
    """Fill in the result on the row inserted at the start. False if Supabase refused."""
    try:
        _request("PATCH", f"/rest/v1/designs?id=eq.{design_id}", user.token, body=row)
    except AuthError:
        return False
    return True


def budget_status() -> dict[str, int] | None:
    """Month's simulation use for /health and the web app, read with the public key alone."""
    if not enabled():
        return None
    try:
        used = sim_ms_used_this_month(os.environ["CIRCUITMIND_SUPABASE_ANON_KEY"])
    except AuthError:
        return None
    return {"used_ms": used, "total_ms": MONTH_BUDGET_MS, "stop_at_ms": int(MONTH_BUDGET_MS * BUDGET_STOP_AT)}
