"""Tests for Appendix A — per-user time-windowed gamification override.

Covers:
- User.gamification_override column round-trips (on / off / null)
- resolve_gamification_enabled: override wins over stable md5 bucketing
- /api/user_status reflects the override
- admin set-override endpoint sets the column AND records a toggle event
"""

from app.models import Event, User
from app.routers.user import create_jwt_token


def _ensure_admin(db) -> User:
    admin = db.query(User).filter(User.openid == "web_admin").first()
    if not admin:
        admin = User(openid="web_admin")
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return admin


def _admin_auth(admin: User) -> dict:
    return {"Authorization": f"Bearer {create_jwt_token(admin.id)}"}


# ── A1: column round-trip ──────────────────────────────────────────────────────


def test_gamification_override_column_round_trips(db):
    user = User(openid="ovr_round_trip", gamification_override="off")
    db.add(user)
    db.commit()
    db.refresh(user)
    assert user.gamification_override == "off"

    user.gamification_override = None
    db.commit()
    db.refresh(user)
    assert user.gamification_override is None
