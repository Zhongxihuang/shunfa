from datetime import date, datetime, timedelta
import pytz

CST = pytz.timezone("Asia/Shanghai")


def get_today_cst() -> date:
    """Get today's date in China Standard Time."""
    return datetime.now(CST).date()


def get_now_cst() -> datetime:
    """Get current datetime in China Standard Time."""
    return datetime.now(CST)


def is_consecutive_day(date1: date, date2: date) -> bool:
    """Check if date2 is exactly one day after date1."""
    return (date2 - date1) == timedelta(days=1)
