import json
from datetime import datetime, timedelta

import httpx
from sqlalchemy.orm import Session

from ..config import settings
from ..models import CheckIn, CheckInStatus, ReminderDelivery, User
from ..utils.time_utils import get_now_cst, get_today_cst, is_reminder_time_active

_WECHAT_ACCESS_TOKEN: str | None = None
_WECHAT_ACCESS_TOKEN_EXPIRES_AT: datetime | None = None

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


def is_wechat_reminder_configured() -> bool:
    return bool(
        settings.wechat_app_id
        and settings.wechat_app_secret
        and settings.wechat_subscribe_template_id
        and settings.wechat_subscribe_page
    )


async def get_wechat_access_token(force_refresh: bool = False) -> str:
    global _WECHAT_ACCESS_TOKEN, _WECHAT_ACCESS_TOKEN_EXPIRES_AT

    now = datetime.utcnow()
    if (
        not force_refresh
        and _WECHAT_ACCESS_TOKEN
        and _WECHAT_ACCESS_TOKEN_EXPIRES_AT
        and now < _WECHAT_ACCESS_TOKEN_EXPIRES_AT
    ):
        return _WECHAT_ACCESS_TOKEN

    if not settings.wechat_app_id or not settings.wechat_app_secret:
        raise ValueError("WeChat app credentials are not configured")

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.weixin.qq.com/cgi-bin/token",
            params={
                "grant_type": "client_credential",
                "appid": settings.wechat_app_id,
                "secret": settings.wechat_app_secret,
            },
        )
        response.raise_for_status()
        data = response.json()

    if data.get("errcode"):
        raise ValueError(f"WeChat token error: {data.get('errmsg', 'unknown error')}")

    token = data.get("access_token")
    expires_in = int(data.get("expires_in", 7200))
    if not token:
        raise ValueError("WeChat access token missing in response")

    _WECHAT_ACCESS_TOKEN = token
    _WECHAT_ACCESS_TOKEN_EXPIRES_AT = now + timedelta(seconds=max(expires_in - 300, 60))
    return token


def build_reminder_payload(openid: str, reminder_time: str | None = None) -> dict:
    now = get_now_cst()
    data = {
        settings.wechat_subscribe_thing_key: {
            "value": "今天这条还没发",
        },
        settings.wechat_subscribe_time_key: {
            "value": reminder_time or now.strftime("%H:%M"),
        },
        settings.wechat_subscribe_phrase_key: {
            "value": "先发了再说",
        },
    }

    if settings.wechat_subscribe_project_key:
        data[settings.wechat_subscribe_project_key] = {
            "value": "顺发",
        }

    return {
        "touser": openid,
        "template_id": settings.wechat_subscribe_template_id,
        "page": settings.wechat_subscribe_page,
        "data": data,
    }


def _get_delivery_for_today(user_id: int, db: Session) -> ReminderDelivery | None:
    return db.query(ReminderDelivery).filter(
        ReminderDelivery.user_id == user_id,
        ReminderDelivery.reminder_date == get_today_cst(),
        ReminderDelivery.channel == "wechat_subscribe",
    ).first()


async def send_wechat_reminder(user: User, db: Session) -> dict:
    if not is_wechat_reminder_configured():
        return {"sent": False, "status": "skipped", "reason": "not_configured"}

    if not check_reminder_needed(user, db):
        return {"sent": False, "status": "skipped", "reason": "not_due"}

    existing = _get_delivery_for_today(user.id, db)
    if existing and existing.status == "sent":
        return {"sent": False, "status": "skipped", "reason": "already_sent"}

    token = await get_wechat_access_token()
    payload = build_reminder_payload(user.openid, user.reminder_time)
    url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        data = response.json()

    status = "sent" if data.get("errcode", 0) == 0 else "failed"
    delivery = existing or ReminderDelivery(
        user_id=user.id,
        reminder_date=get_today_cst(),
        channel="wechat_subscribe",
    )
    delivery.status = status
    delivery.response_payload = json.dumps(data, ensure_ascii=False)
    delivery.sent_at = get_now_cst()
    if existing is None:
        db.add(delivery)
    db.commit()

    return {
        "sent": status == "sent",
        "status": status,
        "reason": None if status == "sent" else data.get("errmsg", "send_failed"),
    }


async def send_due_reminders(db: Session) -> dict:
    users = db.query(User).filter(
        User.reminder_enabled.is_(True),
        User.reminder_time.isnot(None),
    ).all()

    sent = 0
    skipped = 0
    failed = 0

    for user in users:
        try:
            result = await send_wechat_reminder(user, db)
        except Exception:
            failed += 1
            continue

        if result["status"] == "sent":
            sent += 1
        elif result["status"] == "failed":
            failed += 1
        else:
            skipped += 1

    return {
        "sent": sent,
        "skipped": skipped,
        "failed": failed,
        "checked": len(users),
    }
