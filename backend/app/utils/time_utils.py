from datetime import date, datetime, timedelta

import pytz

CST = pytz.timezone("Asia/Shanghai")


def get_today_cst() -> date:
    """Get today's date in China Standard Time.

    Anchored to 08:00 CST as the logical day boundary — running the cron
    at 20:00 or 03:00 both land on the same logical "today". This avoids
    the UTC-midnight crossover (20:00 CST = 12:00 UTC = next UTC calendar day).
    """
    now_sh = datetime.now(CST)
    if now_sh.hour < 8:
        now_sh = now_sh - timedelta(days=1)
    return now_sh.date()


def get_now_cst() -> datetime:
    """Get current datetime in China Standard Time."""
    return datetime.now(CST)


def is_consecutive_day(date1: date, date2: date) -> bool:
    """Check if date2 is exactly one day after date1."""
    return (date2 - date1) == timedelta(days=1)


def is_reminder_time_active(reminder_time: str, now: datetime) -> bool:
    """Check if current time is within 2 hours after reminder_time."""
    try:
        hour, minute = map(int, reminder_time.split(":"))
        reminder_dt = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if reminder_dt > now:
            reminder_dt = reminder_dt - timedelta(hours=24)
        diff = (now - reminder_dt).total_seconds()
        return 0 <= diff <= 7200  # within 2 hours
    except (ValueError, AttributeError):
        return False
