import pytest
import json
from app.models import User, CheckIn, CheckInStatus, Achievement
from app.services.achievement_service import check_and_unlock, get_user_achievements
from app.utils.time_utils import get_today_cst

@pytest.fixture
def user(db):
    u = User(openid="achievement_test_user", streak=0, points=0)
    db.add(u); db.commit(); db.refresh(u)
    return u

@pytest.fixture
def checkin(user, db):
    today = get_today_cst()
    c = CheckIn(
        user_id=user.id,
        date=today,
        topic="测试话题",
        status=CheckInStatus.completed,
        content="内容",
        conversation_history=json.dumps([
            {"role": "user", "content": "msg1"},
            {"role": "assistant", "content": "reply1"},
        ])
    )
    db.add(c); db.commit(); db.refresh(c)
    return c

def test_first_post_unlocked(user, checkin, db):
    user.streak = 1
    user.points = 30
    db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "first_post" in types

def test_streak_3_unlocked(user, checkin, db):
    user.streak = 3
    user.points = 90
    db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "streak_3" in types

def test_streak_7_unlocked(user, checkin, db):
    user.streak = 7
    user.points = 50
    db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "streak_7" in types

def test_achievement_not_duplicated(user, checkin, db):
    user.streak = 1; user.points = 30; db.commit()
    first = check_and_unlock(user, checkin, db)
    db.expire_all()
    second = check_and_unlock(user, checkin, db)
    # first_post 只应出现在第一次
    second_types = [u["type"] for u in second]
    assert "first_post" not in second_types

def test_quality_writer_requires_3_rounds(user, checkin, db):
    # 只有2轮，不触发
    checkin.conversation_history = json.dumps([
        {"role": "user", "content": "1"}, {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"}, {"role": "assistant", "content": "b"},
    ])
    db.commit()
    user.streak = 1; user.points = 30; db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "quality_writer" not in types

def test_quality_writer_with_3_rounds(user, checkin, db):
    checkin.conversation_history = json.dumps([
        {"role": "user", "content": "1"}, {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"}, {"role": "assistant", "content": "b"},
        {"role": "user", "content": "3"}, {"role": "assistant", "content": "c"},
    ])
    db.commit()
    user.streak = 1; user.points = 30; db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "quality_writer" in types

def test_century_points(user, checkin, db):
    user.streak = 1; user.points = 105; db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "century_points" in types

def test_get_user_achievements(user, checkin, db):
    user.streak = 1; user.points = 30; db.commit()
    check_and_unlock(user, checkin, db)
    db.expire_all()
    items = get_user_achievements(user)
    assert len(items) >= 1
    assert all("name" in i and "type" in i for i in items)


def test_quality_writer_excludes_angle_suggestions(user, checkin, db):
    checkin.conversation_history = json.dumps([
        {"role": "user", "content": "__auto_suggest_angles__", "marker": "__angle_suggestion__"},
        {"role": "assistant", "content": "角度A", "marker": "__angle_suggestion__"},
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "a"},
        {"role": "user", "content": "2"},
        {"role": "assistant", "content": "b"},
    ])
    db.commit()
    user.streak = 1; user.points = 30; db.commit()
    unlocked = check_and_unlock(user, checkin, db)
    types = [u["type"] for u in unlocked]
    assert "quality_writer" not in types
