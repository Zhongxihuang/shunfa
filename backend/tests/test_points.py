import pytest
import json
from datetime import datetime, timezone
from app.models import User, CheckIn, CheckInStatus
from app.services.points_service import (
    calculate_points_earned, calculate_level, calculate_diamonds,
    apply_points_and_update_user, LEVEL_THRESHOLDS
)
from app.utils.time_utils import get_today_cst

@pytest.fixture
def user(db):
    u = User(openid="points_test_user", streak=1)
    db.add(u)
    db.commit()
    db.refresh(u)
    return u

@pytest.fixture
def checkin(user, db):
    today = get_today_cst()
    c = CheckIn(
        user_id=user.id,
        date=today,
        topic="测试话题",
        status=CheckInStatus.pending,
        content="测试内容",
        conversation_history=json.dumps([
            {"role": "user", "content": "消息1"},
            {"role": "assistant", "content": "回复1"}
        ])
    )
    db.add(c)
    db.commit()
    db.refresh(c)
    return c

def test_calculate_level_thresholds():
    assert calculate_level(0) == 1
    assert calculate_level(99) == 1
    assert calculate_level(100) == 2
    assert calculate_level(299) == 2
    assert calculate_level(300) == 3
    assert calculate_level(700) == 4
    assert calculate_level(1500) == 5
    assert calculate_level(3100) == 6
    assert calculate_level(6300) == 7
    assert calculate_level(9999) == 7

def test_calculate_diamonds():
    assert calculate_diamonds(0) == 3
    assert calculate_diamonds(100) == 4
    assert calculate_diamonds(250) == 5
    assert calculate_diamonds(1000) == 13

def test_base_points(user, checkin):
    result = calculate_points_earned(checkin, user)
    assert result["base"] == 30
    assert result["topic_bonus"] == 10

def test_streak_bonus_capped(user, checkin):
    """Streak bonus maxes at +30 (6+ day streak)."""
    user.streak = 6
    assert calculate_points_earned(checkin, user)["streak_bonus"] == 30

    user.streak = 10
    assert calculate_points_earned(checkin, user)["streak_bonus"] == 30

    user.streak = 1
    assert calculate_points_earned(checkin, user)["streak_bonus"] == 5

def test_discussion_bonus_capped(user, checkin, db):
    """Discussion bonus maxes at +9 (3 user rounds)."""
    # 3 user rounds
    checkin.conversation_history = json.dumps([
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b"},
        {"role": "user", "content": "3"},
        {"role": "assistant", "content": "c"},
    ])
    assert calculate_points_earned(checkin, user)["discussion_bonus"] == 9

    # 4 user rounds - still 9
    checkin.conversation_history = json.dumps([
        {"role": "user", "content": "1"}, {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"}, {"role": "assistant", "content": "b"},
        {"role": "user", "content": "3"}, {"role": "assistant", "content": "c"},
        {"role": "user", "content": "4"}, {"role": "assistant", "content": "d"},
    ])
    assert calculate_points_earned(checkin, user)["discussion_bonus"] == 9

def test_on_time_bonus(user, checkin, db):
    """On-time bonus when reminder enabled and publish is within 2 hours."""
    from app.utils.time_utils import get_now_cst
    now = get_now_cst()
    # Set reminder to 30 minutes ago
    reminder_hour = now.hour
    reminder_minute = max(0, now.minute - 30)
    user.reminder_enabled = True
    user.reminder_time = f"{reminder_hour:02d}:{reminder_minute:02d}"
    db.commit()

    result = calculate_points_earned(checkin, user)
    assert result["on_time_bonus"] == 5

def test_no_on_time_bonus_reminder_disabled(user, checkin):
    """No on-time bonus when reminder is disabled."""
    user.reminder_enabled = False
    result = calculate_points_earned(checkin, user)
    assert result["on_time_bonus"] == 0

def test_apply_points_updates_user(user, checkin, db):
    """Test that apply_points_and_update_user correctly updates user."""
    user.streak = 1
    initial_points = user.points

    result = apply_points_and_update_user(user, checkin, db)

    assert result["points_earned"] > 0

    db.expire_all()
    updated_user = db.query(User).filter(User.id == user.id).first()
    assert updated_user.points == initial_points + result["points_earned"]

def test_level_updates_after_points(user, checkin, db):
    """Test that level is recalculated after earning points."""
    user.points = 95  # Just below level 2 threshold (100)
    db.commit()

    result = apply_points_and_update_user(user, checkin, db)

    # Should have crossed 100 points threshold
    assert result["total_points"] >= 100
    assert result["level"] >= 2


def test_discussion_bonus_excludes_angle_suggestions(user, checkin):
    checkin.conversation_history = json.dumps([
        {"role": "user", "content": "__auto_suggest_angles__", "marker": "__angle_suggestion__"},
        {"role": "assistant", "content": "角度A", "marker": "__angle_suggestion__"},
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "draft"},
    ])
    result = calculate_points_earned(checkin, user)
    assert result["discussion_bonus"] == 3
