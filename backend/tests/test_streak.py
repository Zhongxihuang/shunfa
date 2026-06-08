from datetime import timedelta

import pytest

from app.models import User
from app.services.streak_service import calculate_and_update_streak
from app.utils.time_utils import get_today_cst


@pytest.fixture
def user(db):
    u = User(openid="streak_test_user")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def test_first_checkin_streak_is_one(user, db):
    today = get_today_cst()
    streak = calculate_and_update_streak(user, today, db)
    assert streak == 1
    assert user.streak == 1
    assert user.longest_streak == 1


def test_consecutive_day_increments_streak(user, db):
    yesterday = get_today_cst() - timedelta(days=1)
    user.streak = 3
    user.last_checkin_date = yesterday
    db.commit()

    today = get_today_cst()
    streak = calculate_and_update_streak(user, today, db)
    assert streak == 4
    assert user.streak == 4


def test_gap_resets_streak(user, db):
    two_days_ago = get_today_cst() - timedelta(days=2)
    user.streak = 5
    user.streak_freezes = 0  # no protection card → the gap should reset
    user.last_checkin_date = two_days_ago
    db.commit()

    today = get_today_cst()
    streak = calculate_and_update_streak(user, today, db)
    assert streak == 1
    assert user.streak == 1


def test_longest_streak_updated(user, db):
    yesterday = get_today_cst() - timedelta(days=1)
    user.streak = 9
    user.longest_streak = 9
    user.last_checkin_date = yesterday
    db.commit()

    today = get_today_cst()
    streak = calculate_and_update_streak(user, today, db)
    assert streak == 10
    assert user.longest_streak == 10


def test_longest_streak_not_decreased(user, db):
    """Gap resets streak but longest_streak is preserved."""
    two_days_ago = get_today_cst() - timedelta(days=2)
    user.streak = 3
    user.longest_streak = 15
    user.streak_freezes = 0  # no protection card → the gap should reset
    user.last_checkin_date = two_days_ago
    db.commit()

    today = get_today_cst()
    streak = calculate_and_update_streak(user, today, db)
    assert streak == 1
    assert user.longest_streak == 15  # preserved


def test_same_day_no_change(user, db):
    """If last_checkin_date is today, streak doesn't change."""
    today = get_today_cst()
    user.streak = 5
    user.last_checkin_date = today
    db.commit()

    streak = calculate_and_update_streak(user, today, db)
    assert streak == 5


def test_midnight_boundary(user, db):
    """Verify consecutive check is date-based, not time-based."""
    yesterday = get_today_cst() - timedelta(days=1)
    user.streak = 1
    user.last_checkin_date = yesterday
    db.commit()

    today = get_today_cst()
    streak = calculate_and_update_streak(user, today, db)
    assert streak == 2
