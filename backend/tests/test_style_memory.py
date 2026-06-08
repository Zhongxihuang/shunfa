"""Tests for the style-memory learning loop.

The style memory aggregates a user's past 👎 content feedback (reason tags +
free-text notes) into a compact instruction string that is injected into future
draft generation via the `extra_requirements` mechanism.
"""

import json
from datetime import timedelta

from app.models import CheckIn, CheckInStatus, User
from app.services.style_memory import build_style_memory
from app.utils.time_utils import get_now_cst, get_today_cst


def _make_user(db, openid="style_user") -> User:
    user = User(openid=openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _make_checkin(
    db,
    user_id,
    *,
    days_ago=0,
    feedback=None,
    reason_tags=None,
    free_text=None,
    topic="某热点",
):
    context = {}
    if reason_tags is not None:
        context["feedback_reason_tags"] = reason_tags
    if free_text is not None:
        context["feedback_free_text"] = free_text
    checkin = CheckIn(
        user_id=user_id,
        date=get_today_cst() - timedelta(days=days_ago),
        topic=topic,
        status=CheckInStatus.completed,
        content_feedback=feedback,
        content_feedback_at=get_now_cst() - timedelta(days=days_ago) if feedback else None,
        generation_context=json.dumps(context, ensure_ascii=False) if context else None,
    )
    db.add(checkin)
    db.commit()
    return checkin


def test_no_feedback_returns_empty(db):
    """A user with no feedback history has no style memory."""
    user = _make_user(db)
    _make_checkin(db, user.id)
    assert build_style_memory(db, user.id) == ""


def test_up_feedback_alone_returns_empty(db):
    """Positive feedback carries no actionable correction."""
    user = _make_user(db)
    _make_checkin(db, user.id, feedback="up")
    assert build_style_memory(db, user.id) == ""


def test_down_with_known_reason_tag_maps_to_instruction(db):
    """A 👎 with the 'too_flat' tag yields a sharpness instruction."""
    user = _make_user(db)
    _make_checkin(db, user.id, feedback="down", reason_tags=["too_flat"])
    memory = build_style_memory(db, user.id)
    assert memory != ""
    assert "锐" in memory or "立场" in memory


def test_down_with_free_text_is_included(db):
    """The user's own words are the strongest signal and must surface verbatim."""
    user = _make_user(db)
    _make_checkin(db, user.id, feedback="down", free_text="少用感叹号，语气平实一点")
    memory = build_style_memory(db, user.id)
    assert "少用感叹号" in memory


def test_only_considers_target_user(db):
    """Feedback from other users must not leak into this user's memory."""
    user = _make_user(db, openid="user_a")
    other = _make_user(db, openid="user_b")
    _make_checkin(db, other.id, feedback="down", free_text="别人的偏好")
    assert build_style_memory(db, user.id) == ""


def test_duplicate_reason_tags_dedupe(db):
    """Repeated tags across check-ins collapse into a single instruction."""
    user = _make_user(db)
    _make_checkin(db, user.id, days_ago=0, feedback="down", reason_tags=["too_flat"])
    _make_checkin(db, user.id, days_ago=1, feedback="down", reason_tags=["too_flat"])
    memory = build_style_memory(db, user.id)
    lines = [line for line in memory.splitlines() if line.strip()]
    # No duplicated identical lines.
    assert len(lines) == len(set(lines))


def test_respects_limit(db):
    """Only the most recent feedback within the limit is considered."""
    user = _make_user(db)
    for i in range(12):
        _make_checkin(
            db, user.id, days_ago=i, feedback="down", free_text=f"偏好{i}", topic=f"热点{i}"
        )
    memory = build_style_memory(db, user.id, limit=5)
    assert memory != ""
    # The oldest note (偏好11, outside the limit window) must not appear.
    assert "偏好11" not in memory
