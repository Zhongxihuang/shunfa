"""Entry-loop free trial ("先爽后配").

New users get a small number of free generations on the platform's shared
DeepSeek key before being asked to bring their own. This removes the BYOK hard
wall that was the first drop-off point in the funnel.

Design:
- The shared key is `settings.deepseek_api_key` (the platform's own key).
- The per-user counter is `User.free_quota_used`; the cap is
  `settings.free_quota_limit` (0 disables the feature entirely).
- A "use" is charged once per successfully produced **draft**, not per AI call,
  so multi-round discussion stays free within a draft's budget. The dependency
  only gates (allow while remaining > 0); the charge happens in the endpoint
  after the draft is produced — see `app/routers/content.py`.

All tracking is best-effort via `analytics.track` and never breaks the flow.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from ..config import settings
from ..models import User
from .analytics import track


def free_quota_limit() -> int:
    """The configured number of free generations per user (>= 0)."""
    return max(0, settings.free_quota_limit)


def free_quota_enabled() -> bool:
    """True when the free trial is on AND a shared key exists to back it."""
    return free_quota_limit() > 0 and bool(settings.deepseek_api_key)


def free_quota_remaining(user: User) -> int:
    """How many free generations this user has left (never negative)."""
    return max(0, free_quota_limit() - (user.free_quota_used or 0))


def consume_free_quota(db: Session, user: User) -> int:
    """Charge one free generation to the user and record it.

    Call exactly once per successful free draft. Returns the new remaining
    count. Tracking failures never raise.
    """
    user.free_quota_used = (user.free_quota_used or 0) + 1
    db.commit()
    remaining = free_quota_remaining(user)
    track(
        "free_quota_used",
        user_id=user.id,
        props={
            "used": user.free_quota_used,
            "limit": free_quota_limit(),
            "remaining": remaining,
        },
    )
    return remaining
