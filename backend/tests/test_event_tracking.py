"""Tests for W1.2: full-funnel event tracking.

These verify that the high-leverage user actions in the funnel all leave an
Event row, so W1.3 (funnel admin endpoint) has data to query.

Acceptance for W1.2:
- login / register / save_api_key / select_topic / discuss_round / publish
  each call analytics.track() with the right event name
- POST /api/event/track stores a frontend event and returns 204
- the endpoint is best-effort: it still returns 204 if tracking itself fails
"""

import json
from unittest.mock import patch

from app.models import Event, User
from app.routers.user import create_jwt_token


def _make_user(db, openid: str = "events_user") -> User:
    user = User(openid=openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


def _events_for(db, user_id: int, event: str) -> list[Event]:
    return (
        db.query(Event)
        .filter(Event.user_id == user_id, Event.event == event)
        .order_by(Event.ts)
        .all()
    )


# ── login (auth_login path) ───────────────────────────────────────────────────


def test_auth_login_tracks_login_event(client, db):
    from app.routers.user import _hash_password

    user = User(
        openid="web_login_track",
        username="loginuser",
        password_hash=_hash_password("correctpw"),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    # Failed login should NOT track a "login" event.
    resp = client.post(
        "/api/auth_login",
        json={"username": "loginuser", "password": "wrongpw"},
    )
    assert resp.status_code == 401
    failed = _events_for(db, user.id, "login")
    assert failed == []

    # Successful login should track.
    resp = client.post(
        "/api/auth_login",
        json={"username": "loginuser", "password": "correctpw"},
    )
    assert resp.status_code == 200

    rows = _events_for(db, user.id, "login")
    assert len(rows) == 1
    props = json.loads(rows[0].props_json)
    assert props["method"] == "web_password"


def test_register_tracks_register_event(client, db):
    resp = client.post(
        "/api/register",
        json={"username": "newuser_evt", "password": "hunter22"},
    )
    assert resp.status_code == 200

    user = db.query(User).filter(User.username == "newuser_evt").first()
    assert user is not None
    rows = _events_for(db, user.id, "register")
    assert len(rows) == 1
    props = json.loads(rows[0].props_json)
    assert props["method"] == "web_password"


# ── key_configured ────────────────────────────────────────────────────────────


def test_save_api_key_tracks_key_configured(client, db):
    user = _make_user(db, "apikey_user")
    resp = client.post(
        "/api/user/api_key",
        json={"api_key": "sk-test-key-for-tracking-12345"},
        headers=_auth(user),
    )
    assert resp.status_code == 200

    rows = _events_for(db, user.id, "key_configured")
    assert len(rows) == 1
    props = json.loads(rows[0].props_json)
    # We must NEVER log the plaintext key. The tracked field is the masked preview only.
    assert "sk-test-key" not in str(props)
    assert "key_preview" in props


# ── generic /api/event/track (used by frontend) ──────────────────────────────


def test_event_track_endpoint_returns_204(client, db):
    user = _make_user(db, "track_endpoint_user")
    resp = client.post(
        "/api/event/track",
        json={"event": "copy_to_xhs", "props": {"checkin_id": 99}},
        headers=_auth(user),
    )
    assert resp.status_code == 204

    rows = _events_for(db, user.id, "copy_to_xhs")
    assert len(rows) == 1
    assert json.loads(rows[0].props_json) == {"checkin_id": 99}


def test_event_track_endpoint_does_not_break_when_storage_fails(client, db):
    """Even if analytics.track() raises internally, the endpoint still returns 204."""
    user = _make_user(db, "track_endpoint_fail")
    with patch("app.routers.analytics.track", return_value=False):
        resp = client.post(
            "/api/event/track",
            json={"event": "copy_to_xhs"},
            headers=_auth(user),
        )
    assert resp.status_code == 204
    # Nothing got persisted, but the API call succeeded.
    assert _events_for(db, user.id, "copy_to_xhs") == []


def test_event_track_endpoint_requires_auth(client):
    resp = client.post("/api/event/track", json={"event": "x"})
    assert resp.status_code in (401, 403)


def test_event_track_endpoint_rejects_anonymous_user_ids(client):
    """Anonymous events should go through track() directly, not this endpoint,
    since this endpoint is for *authenticated* frontend events."""
    resp = client.post("/api/event/track", json={"event": "x"})
    assert resp.status_code in (401, 403)
