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


# ── A2: resolve_gamification_enabled ───────────────────────────────────────────


def test_resolve_override_on_forces_enabled():
    from app.services.feature_flags import resolve_gamification_enabled

    user = User(openid="ovr_on", gamification_override="on")
    assert resolve_gamification_enabled(user) is True


def test_resolve_override_off_forces_disabled():
    from app.services.feature_flags import resolve_gamification_enabled

    user = User(openid="ovr_off", gamification_override="off")
    assert resolve_gamification_enabled(user) is False


def test_resolve_null_falls_back_to_stable_bucket():
    from app.services.feature_flags import gamification_enabled, resolve_gamification_enabled

    user = User(openid="ovr_null", gamification_override=None)
    user.id = 4242  # bucketing is a pure function of id
    assert resolve_gamification_enabled(user) == gamification_enabled(4242)


# ── A3: user_status reflects the override ──────────────────────────────────────


def test_user_status_reflects_override_off(client, db):
    user = User(openid="ovr_status_off", gamification_override="off")
    db.add(user)
    db.commit()
    db.refresh(user)
    resp = client.get(
        "/api/user_status",
        headers={"Authorization": f"Bearer {create_jwt_token(user.id)}"},
    )
    assert resp.status_code == 200
    assert resp.json()["gamification_enabled"] is False


def test_user_status_reflects_override_on(client, db):
    user = User(openid="ovr_status_on", gamification_override="on")
    db.add(user)
    db.commit()
    db.refresh(user)
    resp = client.get(
        "/api/user_status",
        headers={"Authorization": f"Bearer {create_jwt_token(user.id)}"},
    )
    assert resp.status_code == 200
    assert resp.json()["gamification_enabled"] is True


# ── A4: admin set-override endpoint + toggle event ─────────────────────────────


def test_set_override_requires_admin(client, db):
    user = User(openid="ovr_regular")
    db.add(user)
    db.commit()
    db.refresh(user)
    resp = client.post(
        "/api/admin/gamification_override",
        json={"user_id": user.id, "override": "off"},
        headers={"Authorization": f"Bearer {create_jwt_token(user.id)}"},
    )
    assert resp.status_code == 403


def test_set_override_404_for_unknown_user(client, db):
    admin = _ensure_admin(db)
    resp = client.post(
        "/api/admin/gamification_override",
        json={"user_id": 999999, "override": "off"},
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 404


def test_set_override_rejects_bad_value(client, db):
    admin = _ensure_admin(db)
    target = User(openid="ovr_badval")
    db.add(target)
    db.commit()
    db.refresh(target)
    resp = client.post(
        "/api/admin/gamification_override",
        json={"user_id": target.id, "override": "maybe"},
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 400


def test_set_override_sets_column_and_records_toggle(client, db):
    admin = _ensure_admin(db)
    target = User(openid="ovr_set")
    db.add(target)
    db.commit()
    db.refresh(target)

    resp = client.post(
        "/api/admin/gamification_override",
        json={"user_id": target.id, "override": "off"},
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["gamification_override"] == "off"
    assert body["from"] == "default"
    assert body["to"] == "off"

    db.refresh(target)
    assert target.gamification_override == "off"

    toggles = (
        db.query(Event)
        .filter(Event.user_id == target.id, Event.event == "gamification_override_changed")
        .all()
    )
    assert len(toggles) == 1

    # Flip back to "on": from-value must reflect the previous "off".
    resp2 = client.post(
        "/api/admin/gamification_override",
        json={"user_id": target.id, "override": "on"},
        headers=_admin_auth(admin),
    )
    assert resp2.status_code == 200
    assert resp2.json()["from"] == "off"
    assert resp2.json()["to"] == "on"


def test_set_override_null_clears_column(client, db):
    admin = _ensure_admin(db)
    target = User(openid="ovr_clear", gamification_override="off")
    db.add(target)
    db.commit()
    db.refresh(target)

    resp = client.post(
        "/api/admin/gamification_override",
        json={"user_id": target.id, "override": None},
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    assert resp.json()["gamification_override"] is None
    assert resp.json()["to"] == "default"
    db.refresh(target)
    assert target.gamification_override is None
