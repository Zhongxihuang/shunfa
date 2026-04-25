"""
Content service — coordinates the atomic publish flow across streak, points, and achievements.

This module deliberately does NOT import from draft_service or discussion_service
to avoid circular dependencies. Use those modules directly from routers.
"""

from sqlalchemy.orm import Session

from ..models import CheckIn, CheckInStatus, User
from ..utils.time_utils import get_now_cst

# ── Public re-exports (used by routers, kept for backward compatibility) ───────
# Sentinel values — re-exported so existing imports keep working
from .discussion_service import (  # noqa: F401
    ANGLE_HISTORY_MARKER,
    AUTO_SUGGEST_SENTINEL,
    MAX_DISCUSSION_ROUNDS,
    MIN_DISCUSSION_ROUNDS,
    REFRESH_ANGLES_SENTINEL,
)
from .draft_service import (  # noqa: F401
    build_quick_generate_context,
    build_quick_generate_context_from_checkin,
    quick_generate,
)


async def confirm_publish(checkin: CheckIn, db: Session, user: User) -> dict:
    """
    User confirms publish. Updates checkin to completed.

    This function is ATOMIC - all DB changes are committed in a single transaction
    to ensure data consistency across streak, points, and achievements.
    """
    if checkin.status == CheckInStatus.completed:
        raise ValueError("今日已完成发布，请勿重复提交")
    if checkin.status != CheckInStatus.pending:
        raise ValueError("请先确认内容后再发布")

    # Import here to avoid circular imports
    from ..utils.time_utils import get_today_cst
    from .achievement_service import check_and_unlock
    from .points_service import apply_points_and_update_user
    from .streak_service import calculate_and_update_streak

    today = get_today_cst()

    try:
        # 1. Update streak (flushes, no commit)
        new_streak = calculate_and_update_streak(user, today, db)

        # 2. Apply points (flushes, no commit)
        result = apply_points_and_update_user(user, checkin, db)

        # 3. Mark checkin as completed (flushes, no commit)
        checkin.status = CheckInStatus.completed
        checkin.completed_at = get_now_cst()
        db.flush()

        # 4. Check and unlock achievements (flushes new ones, no commit)
        newly_unlocked = check_and_unlock(user, checkin, db)

        # 5. Single atomic commit — everything succeeds or everything fails
        db.commit()

    except Exception:
        db.rollback()
        raise

    message = _get_celebratory_message(new_streak, result["points_earned"])

    return {
        "streak": new_streak,
        "points_earned": result["points_earned"],
        "total_points": result["total_points"],
        "level": result["level"],
        "diamonds": result["diamonds"],
        "message": message,
        "newly_unlocked": newly_unlocked,
    }


def _get_celebratory_message(streak: int, points_earned: int) -> str:
    """Generate a celebratory message based on streak."""
    if streak == 1:
        return f"太棒了！已连更1天，赚取{points_earned}积分！"
    elif streak < 7:
        return f"继续保持！已连更{streak}天，赚取{points_earned}积分！"
    elif streak < 30:
        return f"厉害！连更{streak}天了，赚取{points_earned}积分！"
    else:
        return f"传奇！连更{streak}天！赚取{points_earned}积分！"
