"""The Wokwi monthly simulation quota as a state the engine remembers.

wokwi-cli answers "API Error: You have used up your Free plan monthly CI minute
quota" when the 50 free simulated minutes of the month are gone. That says
nothing about the design, so it must never be scored as a simulation failure.
The simulate rung reports it as its own state, the generation loop stops instead
of sending it to the model, a benchmark sweep stops, and the web engine runs
only the free rungs until the quota is back.

The last known state lives in a small JSON file so the API process, the bench
command and the CLI all see what the last simulation learned. The state expires
on the reset date: Wokwi's quota is monthly, and the first day of the next month
is taken as the reset. The dashboard at https://wokwi.com/dashboard/ci is the
source of truth; the engine learns the real answer on its next simulation.
"""

from __future__ import annotations

import datetime as dt
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_FILE = ROOT / "runs" / "wokwi_quota.json"

_MARK = "monthly ci minute quota"


def state_file() -> Path:
    return Path(os.environ.get("CIRCUITMIND_QUOTA_FILE") or _DEFAULT_FILE)


def exhausted_reply(output: str) -> bool:
    """True when wokwi-cli's output is the monthly quota refusal."""
    return _MARK in (output or "").lower()


def reset_date(today: dt.date | None = None) -> dt.date:
    """First day of the month after ``today``: when the monthly quota is expected back."""
    today = today or dt.date.today()
    year, month = (today.year + 1, 1) if today.month == 12 else (today.year, today.month + 1)
    return dt.date(year, month, 1)


def mark_exhausted(message: str = "", today: dt.date | None = None) -> dict:
    """Remember that the simulator refused for quota. Returns the state written."""
    today = today or dt.date.today()
    st = {
        "exhausted": True,
        "since": today.isoformat(),
        "resets": reset_date(today).isoformat(),
        "message": (message or "").strip()[:300],
    }
    _write(st)
    return st


def mark_ok(today: dt.date | None = None) -> None:
    """A simulation ran: whatever we remembered about the quota is stale."""
    today = today or dt.date.today()
    if state_file().exists():
        _write({"exhausted": False, "since": today.isoformat(), "resets": None, "message": ""})


def state(today: dt.date | None = None) -> dict:
    """Last known quota state, with ``exhausted`` False once the reset date has passed.

    Always returns a dict with ``exhausted``, ``since``, ``resets`` and ``notice``;
    ``notice`` is the sentence the web app shows, empty when there is nothing to say.
    """
    today = today or dt.date.today()
    try:
        st = json.loads(state_file().read_text())
    except (OSError, ValueError):
        st = {}
    exhausted = bool(st.get("exhausted"))
    resets = st.get("resets")
    if exhausted and resets:
        try:
            exhausted = today < dt.date.fromisoformat(resets)
        except ValueError:
            pass
    out = {"exhausted": exhausted, "since": st.get("since"), "resets": resets if exhausted else None}
    out["notice"] = notice(out) if exhausted else ""
    return out


def _pretty(iso: str | None) -> str:
    if not iso:
        return "next month"
    try:
        d = dt.date.fromisoformat(iso)
    except ValueError:
        return iso
    return f"{d.day} {d.strftime('%b %Y')}"


def notice(st: dict) -> str:
    """What a person at the web app reads when simulation is off for the month."""
    return (
        f"Simulation minutes for this month are used up (resets {_pretty(st.get('resets'))}). "
        "Designs are checked up to compile and electrical rules only and are shown as unverified."
    )


def _write(st: dict) -> None:
    p = state_file()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(st, indent=2))
