import json
from datetime import date
from sqlalchemy.orm import Session

from ..models import User, CheckIn
from ..utils.time_utils import get_now_cst, is_reminder_time_active
from .content_service import count_real_user_rounds

LEVEL_THRESHOLDS = [0, 100, 300, 700, 1500, 3100, 6300]


def calculate_level(total_points: int) -> int:
    """Calculate level from total points."""
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_points >= threshold:
            level = i + 1
    return level


def calculate_diamonds(total_points: int) -> int:
    """Calculate diamonds from total points."""
    return 3 + (total_points // 100)


def calculate_points_earned(checkin: CheckIn, user: User) -> dict:
    """
    Calculate points earned for a completed check-in.
    Returns breakdown dict with total.
    """
    now = get_now_cst()

    # Base points
    base = 30

    # Streak bonus: +5 per streak day, max +30
    streak_bonus = min(user.streak * 5, 30)

    # Topic bonus (always +10, topic was selected)
    topic_bonus = 10

    # Discussion rounds bonus: +3 per user message, max +9
    history = json.loads(checkin.conversation_history or "[]")
    user_rounds = count_real_user_rounds(history)
    discussion_bonus = min(user_rounds * 3, 9)

    # On-time bonus
    on_time_bonus = 0
    if user.reminder_enabled and user.reminder_time:
        if is_reminder_time_active(user.reminder_time, now):
            on_time_bonus = 5

    total = base + streak_bonus + topic_bonus + discussion_bonus + on_time_bonus

    return {
        "base": base,
        "streak_bonus": streak_bonus,
        "topic_bonus": topic_bonus,
        "discussion_bonus": discussion_bonus,
        "on_time_bonus": on_time_bonus,
        "total": total
    }


def apply_points_and_update_user(
    user: User,
    checkin: CheckIn,
    db: Session
) -> dict:
    """
    Apply points to user and update level/diamonds.
    Returns the points breakdown and new user stats.
    """
    breakdown = calculate_points_earned(checkin, user)
    points_earned = breakdown["total"]

    # Update checkin
    checkin.points_earned = points_earned

    # Update user
    user.points += points_earned
    user.level = calculate_level(user.points)
    user.diamonds = calculate_diamonds(user.points)

    db.commit()

    return {
        "points_earned": points_earned,
        "total_points": user.points,
        "level": user.level,
        "diamonds": user.diamonds,
        "breakdown": breakdown
    }
