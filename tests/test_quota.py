"""The Wokwi monthly quota is a remembered state that expires on the reset date."""

import datetime as dt

import pytest

from circuitmind import quota

REPLY = "API Error: You have used up your Free plan monthly CI minute quota. Please upgrade to a paid plan at https://wokwi.com/pricing."


@pytest.fixture(autouse=True)
def own_state_file(tmp_path, monkeypatch):
    monkeypatch.setenv("CIRCUITMIND_QUOTA_FILE", str(tmp_path / "wokwi_quota.json"))


def test_only_the_quota_reply_counts():
    assert quota.exhausted_reply(REPLY)
    assert quota.exhausted_reply("boot\n" + REPLY.lower())
    assert not quota.exhausted_reply("API Error: Connection to transport closed unexpectedly: code 1006")
    assert not quota.exhausted_reply("")
    assert not quota.exhausted_reply(None)


def test_reset_is_the_first_of_next_month():
    assert quota.reset_date(dt.date(2026, 11, 16)) == dt.date(2026, 12, 1)
    assert quota.reset_date(dt.date(2026, 12, 5)) == dt.date(2027, 1, 1)
    assert quota.reset_date(dt.date(2026, 1, 1)) == dt.date(2026, 2, 1)


def test_nothing_remembered_means_not_exhausted():
    st = quota.state()
    assert st == {"exhausted": False, "since": None, "resets": None, "notice": ""}


def test_marked_state_holds_until_the_reset_date_then_expires():
    st = quota.mark_exhausted(REPLY, today=dt.date(2026, 11, 16))
    assert st["resets"] == "2026-12-01" and st["message"] == REPLY
    later = quota.state(today=dt.date(2026, 11, 30))
    assert later["exhausted"] is True and later["resets"] == "2026-12-01" and later["since"] == "2026-11-16"
    assert later["notice"] == (
        "Simulation minutes for this month are used up (resets 1 Dec 2026). "
        "Designs are checked up to compile and electrical rules only and are shown as unverified."
    )
    reset = quota.state(today=dt.date(2026, 12, 1))
    assert reset["exhausted"] is False and reset["resets"] is None and reset["notice"] == ""


def test_a_run_that_went_through_clears_the_state():
    quota.mark_exhausted(REPLY, today=dt.date(2026, 11, 16))
    quota.mark_ok(today=dt.date(2026, 11, 17))
    assert quota.state(today=dt.date(2026, 11, 17))["exhausted"] is False


def test_mark_ok_without_a_file_writes_nothing():
    quota.mark_ok()
    assert not quota.state_file().exists()


def test_a_broken_state_file_reads_as_not_exhausted():
    quota.state_file().parent.mkdir(parents=True, exist_ok=True)
    quota.state_file().write_text("{not json")
    assert quota.state()["exhausted"] is False
