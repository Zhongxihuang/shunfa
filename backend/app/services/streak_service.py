from datetime import date

from sqlalchemy.orm import Session

from ..models import User
from ..utils.time_utils import is_consecutive_day
from .analytics import track


def calculate_and_update_streak(user: User, today: date, db: Session) -> int:
    """
    Update user streak based on today's check-in.
    Returns the new streak value.

    Streak freeze (W3.8): when the user missed exactly one day and holds a
    protection card, the card is consumed and the streak survives instead of
    resetting to zero. Larger gaps are NOT covered by a single card.
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
    elif (today - last_date).days == 2 and user.streak > 0 and (user.streak_freezes or 0) > 0:
        # Exactly one missed day, and the user has a freeze: spend it to keep
        # the streak alive (and still count today).
        user.streak_freezes -= 1
        new_streak = user.streak + 1
        track(
            "streak_freeze_used",
            user_id=user.id,
            props={"streak": new_streak, "freezes_left": user.streak_freezes},
        )
    else:
        # Gap with no protection - reset
        new_streak = 1

    user.streak = new_streak
    user.last_checkin_date = today

    # Update longest streak
    if new_streak > user.longest_streak:
        user.longest_streak = new_streak

    return new_streak
