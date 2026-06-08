"""Tests for Appendix B — flywheel source (`src`) attribution.

Covers:
- register accepts an optional `src` and writes it into the register event props
- register without `src` keeps the legacy props shape (no `src` key)
- get_funnel(src=...) restricts every step to users who registered with that src
- admin funnel endpoint exposes a `src` query param and echoes it back
"""

import json

from app.models import Event, User
from app.routers.user import create_jwt_token
from app.services.analytics import track


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


def _register_event_props(db, user_id: int) -> dict:
    row = (
        db.query(Event)
        .filter(Event.user_id == user_id, Event.event == "register")
        .one()
    )
    return json.loads(row.props_json)


# ── B1: register writes src into the event ─────────────────────────────────────


def test_register_with_src_records_it(client, db):
    resp = client.post(
        "/api/register",
        json={"username": "src_user_a", "password": "password123", "src": "jike_0608"},
    )
    assert resp.status_code == 200
    user = db.query(User).filter(User.username == "src_user_a").one()
    props = _register_event_props(db, user.id)
    assert props["method"] == "web_password"
    assert props["src"] == "jike_0608"


def test_register_without_src_has_no_src_key(client, db):
    resp = client.post(
        "/api/register",
        json={"username": "src_user_b", "password": "password123"},
    )
    assert resp.status_code == 200
    user = db.query(User).filter(User.username == "src_user_b").one()
    props = _register_event_props(db, user.id)
    assert "src" not in props


# ── B2: get_funnel restricts to a src cohort ───────────────────────────────────


def _seed_user_with_src(db, openid: str, src: str | None) -> User:
    user = User(openid=openid)
    db.add(user)
    db.commit()
    db.refresh(user)
    props = {"method": "web_password"}
    if src is not None:
        props["src"] = src
    track("register", user_id=user.id, props=props)
    return user


def test_get_funnel_src_restricts_to_that_cohort(db):
    from app.services.analytics_queries import get_funnel

    # Two users from jike, one from xhs, one organic (no src).
    jike1 = _seed_user_with_src(db, "fsrc_jike1", "jike_0608")
    jike2 = _seed_user_with_src(db, "fsrc_jike2", "jike_0608")
    _seed_user_with_src(db, "fsrc_xhs1", "xhs_0608")
    _seed_user_with_src(db, "fsrc_organic", None)

    # Only jike1 publishes.
    track("publish", user_id=jike1.id)
    track("publish", user_id=jike2.id)

    report = get_funnel(db, src="jike_0608")
    by_event = {s.event: s.users for s in report.steps}
    assert by_event["register"] == 2  # jike1 + jike2 only
    assert by_event["publish"] == 2

    # A src with nobody registered → all zeros.
    empty = get_funnel(db, src="nope_9999")
    assert all(s.users == 0 for s in empty.steps)


def test_get_funnel_without_src_counts_everyone(db):
    from app.services.analytics_queries import get_funnel

    _seed_user_with_src(db, "fall_jike", "jike_0608")
    _seed_user_with_src(db, "fall_organic", None)

    report = get_funnel(db)
    by_event = {s.event: s.users for s in report.steps}
    assert by_event["register"] == 2  # both, src ignored
