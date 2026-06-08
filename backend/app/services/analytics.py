"""Product analytics — best-effort event tracking.

The point of this module is to make sure **a tracking failure never breaks the
caller's request flow**. `track()` always returns a bool and never raises.

Usage:
    from app.services.analytics import track

    track("publish", user_id=user.id, props={"platform": "wechat"})

Notes:
- Each call opens its own short-lived SessionLocal so we don't entangle the
  caller's session/transaction with the tracking write.
- `props` is JSON-serialized with `ensure_ascii=False` so Chinese strings round-trip.
- `event` is truncated to 64 chars to defend against accidental giant keys.
- Failures are logged at WARNING with the exception type only (not the message
  or any user data) to keep the launch-checklist's "no PII in logs" posture.
"""

import json
import logging
from typing import Any

from ..database import SessionLocal
from ..models import Event

logger = logging.getLogger(__name__)

_MAX_EVENT_NAME_LEN = 64


def track(
    event: str,
    user_id: int | None = None,
    props: dict[str, Any] | None = None,
) -> bool:
    """Record a product event. Best-effort. Returns True on success, False on any failure.

    Args:
        event: short event name, e.g. "publish", "copy_to_xhs", "topic_selected".
        user_id: optional user id; None for anonymous events.
        props: optional dict of event properties (e.g. {"platform": "wechat"}).
    """
    if not event:
        logger.warning("track() called with empty event name")
        return False

    safe_event = event[:_MAX_EVENT_NAME_LEN]
    safe_props_json: str | None = None
    if props is not None:
        try:
            safe_props_json = json.dumps(props, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            logger.warning(
                "track() failed to serialize props for event=%s: %s",
                safe_event,
                type(exc).__name__,
            )
            return False

    try:
        db = SessionLocal()
    except Exception as exc:
        logger.warning(
            "track() could not open session for event=%s: %s",
            safe_event,
            type(exc).__name__,
        )
        return False

    try:
        ev = Event(
            user_id=user_id,
            event=safe_event,
            props_json=safe_props_json,
        )
        db.add(ev)
        db.commit()
        return True
    except Exception as exc:
        try:
            db.rollback()
        except Exception:
            pass
        logger.warning(
            "track() failed to persist event=%s: %s",
            safe_event,
            type(exc).__name__,
        )
        return False
    finally:
        try:
            db.close()
        except Exception:
            pass
