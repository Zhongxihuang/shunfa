from datetime import date
from sqlalchemy.orm import Session

from ..models import User
from ..utils.time_utils import get_today_cst, is_consecutive_day


def calculate_and_update_streak(user: User, today: date, db: Session) -> int:
    """
    Update user streak based on today's check-in.
    Returns the new streak value.
    """
    last_date = user.last_checkin_date

    if last_date is None:
        # First ever check-in
        new_streak = 1
    elif last_date == today:
        # Same day - no change (shouldn't happen due to completed check guard)
        new_streak = user.streak
    elif is_consecutive_day(last_date, today):
        # Consecutive day - increment
        new_streak = user.streak + 1
    else:
        # Gap - reset
        new_streak = 1

    user.streak = new_streak
    user.last_checkin_date = today

    # Update longest streak
    if new_streak > user.longest_streak:
        user.longest_streak = new_streak

    return new_streak
