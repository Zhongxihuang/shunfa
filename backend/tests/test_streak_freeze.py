"""Tests for streak freeze / 断签保护 (W3.8).

Duolingo's strongest retention hook: a "freeze" card saves the streak when a
user misses a day, instead of resetting it to zero. We evaluate it lazily on
the next check-in (no cron needed):

- a single missed day with a freeze available consumes ONE freeze and KEEPS the
  streak climbing (yesterday's miss is forgiven)
- consecutive days never touch a freeze
- a missed day with NO freeze resets to 1 (legacy behaviour preserved)
- a gap larger than one day is NOT covered by a single freeze (resets)
- a freeze save emits a `streak_freeze_used` event for measurement
"""

from datetime import timedelta

from app.models import Event, User
from app.services.streak_service import calculate_and_update_streak
from app.utils.time_utils import get_today_cst


def _make_user(db, **kw) -> User:
    user = User(openid=kw.pop("openid", "freeze_user"), **kw)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _freeze_events(db, user_id):
    return (
        db.query(Event).filter(Event.user_id == user_id, Event.event == "streak_freeze_used").all()
    )


def test_consecutive_day_does_not_use_freeze(db):
    today = get_today_cst()
    user = _make_user(db, streak=3, streak_freezes=1, last_checkin_date=today - timedelta(days=1))
    new_streak = calculate_and_update_streak(user, today, db)
    assert new_streak == 4
    assert user.streak_freezes == 1  # untouched
    assert _freeze_events(db, user.id) == []


def test_single_missed_day_consumes_freeze_and_keeps_streak(db):
    today = get_today_cst()
    # last check-in was 2 days ago → exactly one missed day
    user = _make_user(db, streak=5, streak_freezes=1, last_checkin_date=today - timedelta(days=2))
    new_streak = calculate_and_update_streak(user, today, db)
    assert new_streak == 6  # streak preserved and incremented for today
    assert user.streak_freezes == 0  # one card consumed
    assert len(_freeze_events(db, user.id)) == 1


def test_missed_day_without_freeze_resets(db):
    today = get_today_cst()
    user = _make_user(db, streak=5, streak_freezes=0, last_checkin_date=today - timedelta(days=2))
    new_streak = calculate_and_update_streak(user, today, db)
    assert new_streak == 1
    assert user.streak_freezes == 0
    assert _freeze_events(db, user.id) == []


def test_large_gap_not_saved_by_single_freeze(db):
    today = get_today_cst()
    # missed three days — one freeze can't cover it
    user = _make_user(db, streak=5, streak_freezes=1, last_checkin_date=today - timedelta(days=4))
    new_streak = calculate_and_update_streak(user, today, db)
    assert new_streak == 1
    assert user.streak_freezes == 1  # not wasted on an uncoverable gap
    assert _freeze_events(db, user.id) == []


def test_first_ever_checkin_unaffected(db):
    today = get_today_cst()
    user = _make_user(db, streak=0, streak_freezes=1, last_checkin_date=None)
    new_streak = calculate_and_update_streak(user, today, db)
    assert new_streak == 1
    assert user.streak_freezes == 1
