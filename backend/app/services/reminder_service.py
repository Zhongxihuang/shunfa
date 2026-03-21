from sqlalchemy.orm import Session
from ..models import User, CheckIn, CheckInStatus
from ..utils.time_utils import get_today_cst, get_now_cst, is_reminder_time_active

def check_reminder_needed(user: User, db: Session) -> bool:
    """
    Check if user should be reminded to post today.
    Returns True if:
    - Reminder is enabled
    - Current time is within the reminder window (2h after reminder_time)
    - User hasn't completed today's check-in
    """
    if not user.reminder_enabled or not user.reminder_time:
        return False

    now = get_now_cst()
    if not is_reminder_time_active(user.reminder_time, now):
        return False

    # Check if already completed today
    today = get_today_cst()
    completed = db.query(CheckIn).filter(
        CheckIn.user_id == user.id,
        CheckIn.date == today,
        CheckIn.status == CheckInStatus.completed
    ).first()

    return completed is None

def update_reminder_settings(user: User, reminder_time: str | None, reminder_enabled: bool, db: Session) -> None:
    """Update user's reminder settings."""
    if reminder_time is not None:
        # Validate format HH:MM
        try:
            hour, minute = map(int, reminder_time.split(":"))
            if not (0 <= hour <= 23 and 0 <= minute <= 59):
                raise ValueError("Invalid time")
        except (ValueError, AttributeError):
            raise ValueError("提醒时间格式错误，请使用 HH:MM 格式")

    user.reminder_time = reminder_time
    user.reminder_enabled = reminder_enabled
    db.commit()
