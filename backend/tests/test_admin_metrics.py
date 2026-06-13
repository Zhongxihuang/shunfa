"""Tests for W1.3: admin funnel + north-star metrics endpoint.

Coverage:
- 401/403/404 gating
- empty funnel returns zeros
- full funnel: distinct-user counts per step + conversion rates
- per-user funnel position (furthest step, last event)
- north-star ratio (publishers with streak ≥ 3 / publishers total)
- window_days filter excludes old events
"""

import json
from datetime import timedelta

from app.models import Event, User
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_now_cst


def _admin_token() -> str:
    # We don't have a User row here yet — the endpoint only needs a valid JWT
    # whose payload carries an openid=='web_admin' user_id. The test that uses
    # this builds the admin row first; for the gating tests we pass a bogus id
    # because get_admin_user only checks openid AFTER fetching by id, so we
    # need a real user. Tests that need admin auth build their own token.
    return "placeholder"  # overwritten per-test


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


# ── gating ────────────────────────────────────────────────────────────────────


def test_funnel_requires_auth(client):
    resp = client.get("/api/admin/metrics/funnel")
    # HTTPBearer raises 403 when the header is missing (FastAPI's HTTPBearer
    # default). 401 is reserved for "token was present but invalid". We assert
    # "not 200" — the exact status is dictated by FastAPI's security stack.
    assert resp.status_code in (401, 403)


def test_funnel_rejects_regular_user(client, db):
    user = User(openid="regular_funnel_probe")
    db.add(user)
    db.commit()
    db.refresh(user)
    resp = client.get(
        "/api/admin/metrics/funnel",
        headers={"Authorization": f"Bearer {create_jwt_token(user.id)}"},
    )
    assert resp.status_code == 403


def test_funnel_user_404_for_unknown_user(client, db):
    admin = _ensure_admin(db)
    resp = client.get(
        "/api/admin/metrics/funnel/user/999999",
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 404


# ── empty state ───────────────────────────────────────────────────────────────


def test_funnel_empty_returns_zeros(client, db):
    admin = _ensure_admin(db)
    resp = client.get(
        "/api/admin/metrics/funnel",
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 0
    assert body["since"] is None
    # Every step present, all zero.
    labels = [s["label"] for s in body["funnel"]]
    assert labels == ["注册", "配置 Key", "选题", "讨论", "初稿", "发布"]
    for s in body["funnel"]:
        assert s["users"] == 0
        assert s["conversion_from_first"] == 0
        assert s["conversion_from_prev"] == 0
    # No publisher → ratio 0
    assert body["north_star"]["ratio"] == 0
    assert body["north_star"]["total_publishers"] == 0


# ── full funnel math ──────────────────────────────────────────────────────────


def _emit(db, user: User, event: str, props: dict | None = None) -> None:
    db.add(
        Event(
            user_id=user.id,
            event=event,
            props_json=json.dumps(props, ensure_ascii=False) if props else None,
        )
    )
    db.commit()


def test_funnel_counts_distinct_users_per_step(client, db):
    admin = _ensure_admin(db)
    # 3 users go all the way through; 2 users stop at discuss_round.
    for i in range(3):
        u = User(openid=f"full_{i}")
        db.add(u)
        db.commit()
        db.refresh(u)
        for ev in (
            "register",
            "key_configured",
            "topic_selected",
            "discuss_round",
            "draft_generated",
            "publish",
        ):
            _emit(db, u, ev)
        # Set streak ≥ 3 for north-star numerator.
        u.streak = 5
        db.commit()
    for i in range(2):
        u = User(openid=f"partial_{i}")
        db.add(u)
        db.commit()
        db.refresh(u)
        for ev in ("register", "key_configured", "topic_selected", "discuss_round"):
            _emit(db, u, ev)
    # A user that only registered — should not inflate downstream counts.
    u = User(openid="only_register")
    db.add(u)
    db.commit()
    db.refresh(u)
    _emit(db, u, "register")

    resp = client.get(
        "/api/admin/metrics/funnel",
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    by_event = {s["event"]: s for s in body["funnel"]}

    assert by_event["register"]["users"] == 6  # 3 + 2 + 1
    assert by_event["key_configured"]["users"] == 5  # 3 + 2
    assert by_event["topic_selected"]["users"] == 5
    assert by_event["discuss_round"]["users"] == 5
    assert by_event["draft_generated"]["users"] == 3
    assert by_event["publish"]["users"] == 3

    # Conversion from first: publish / register = 3/6 = 0.5
    assert by_event["publish"]["conversion_from_first"] == 0.5
    # Conversion from prev: discuss_round / topic_selected = 5/5 = 1.0
    assert by_event["discuss_round"]["conversion_from_prev"] == 1.0
    # publish / draft_generated = 3/3 = 1.0
    assert by_event["publish"]["conversion_from_prev"] == 1.0

    # North-star: 3 publishers, all with streak≥3 → ratio 1.0
    assert body["north_star"]["total_publishers"] == 3
    assert body["north_star"]["qualifying_users"] == 3
    assert body["north_star"]["ratio"] == 1.0
    assert body["north_star"]["threshold"] == 3
    assert body["north_star"]["total_registered_users"] >= 6


def test_funnel_duplicate_events_count_one_user(client, db):
    """A user retrying the same event must not inflate the funnel count."""
    admin = _ensure_admin(db)
    u = User(openid="retry_user")
    db.add(u)
    db.commit()
    db.refresh(u)
    for _ in range(5):
        _emit(db, u, "publish")

    resp = client.get(
        "/api/admin/metrics/funnel",
        headers=_admin_auth(admin),
    )
    by_event = {s["event"]: s for s in resp.json()["funnel"]}
    assert by_event["publish"]["users"] == 1


def test_funnel_ignores_anonymous_events(client, db):
    """Events with user_id NULL must not count toward any user funnel."""
    admin = _ensure_admin(db)
    db.add(Event(user_id=None, event="publish"))
    db.commit()

    resp = client.get(
        "/api/admin/metrics/funnel",
        headers=_admin_auth(admin),
    )
    by_event = {s["event"]: s for s in resp.json()["funnel"]}
    assert by_event["publish"]["users"] == 0


def test_funnel_window_days_excludes_old_events(client, db):
    admin = _ensure_admin(db)
    old_user = User(openid="old_user")
    db.add(old_user)
    db.commit()
    db.refresh(old_user)
    # Inject a backdated event row.
    db.add(
        Event(
            user_id=old_user.id,
            event="publish",
            ts=get_now_cst() - timedelta(days=10),
        )
    )
    db.commit()

    # window_days=7 should exclude the 10-day-old event.
    resp = client.get(
        "/api/admin/metrics/funnel?window_days=7",
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["window_days"] == 7
    assert body["since"] is not None
    by_event = {s["event"]: s for s in body["funnel"]}
    assert by_event["publish"]["users"] == 0

    # window_days=30 should include it.
    resp = client.get(
        "/api/admin/metrics/funnel?window_days=30",
        headers=_admin_auth(admin),
    )
    by_event = {s["event"]: s for s in resp.json()["funnel"]}
    assert by_event["publish"]["users"] == 1


# ── north-star: ≥3-day streak ratio ──────────────────────────────────────────


def test_north_star_mixed_streaks(client, db):
    admin = _ensure_admin(db)
    # 4 publishers: streaks 10, 5, 2, 0 → 2 qualify (≥3)
    streaks = [10, 5, 2, 0]
    for i, s in enumerate(streaks):
        u = User(openid=f"ns_{i}", streak=s)
        db.add(u)
        db.commit()
        db.refresh(u)
        _emit(db, u, "publish")
    # Non-publisher with streak 99 must NOT inflate ratio.
    u = User(openid="ns_ghost", streak=99)
    db.add(u)
    db.commit()

    resp = client.get(
        "/api/admin/metrics/funnel",
        headers=_admin_auth(admin),
    )
    ns = resp.json()["north_star"]
    assert ns["total_publishers"] == 4
    assert ns["qualifying_users"] == 2
    assert ns["ratio"] == 0.5


# ── distribution: copy/export among publishers (W1.4 measurement) ─────────────


def test_distribution_empty_returns_zeros(client, db):
    admin = _ensure_admin(db)
    resp = client.get("/api/admin/metrics/funnel", headers=_admin_auth(admin))
    assert resp.status_code == 200
    dist = resp.json()["distribution"]
    assert dist["total_publishers"] == 0
    assert dist["copy_users"] == 0
    assert dist["export_users"] == 0
    assert dist["distributed_users"] == 0
    assert dist["distribution_rate"] == 0


def test_distribution_counts_copy_and_export_among_publishers(client, db):
    admin = _ensure_admin(db)
    # 4 publishers:
    #   u0: published + copied
    #   u1: published + exported
    #   u2: published + copied + exported
    #   u3: published only (no distribution)
    users = []
    for i in range(4):
        u = User(openid=f"dist_{i}")
        db.add(u)
        db.commit()
        db.refresh(u)
        _emit(db, u, "publish")
        users.append(u)
    _emit(db, users[0], "copy_to_xiaohongshu")
    _emit(db, users[1], "export_md")
    _emit(db, users[2], "copy_to_moments")
    _emit(db, users[2], "export_txt")

    resp = client.get("/api/admin/metrics/funnel", headers=_admin_auth(admin))
    dist = resp.json()["distribution"]
    assert dist["total_publishers"] == 4
    assert dist["copy_users"] == 2  # u0, u2
    assert dist["export_users"] == 2  # u1, u2
    assert dist["distributed_users"] == 3  # u0, u1, u2
    assert dist["distribution_rate"] == 0.75  # 3 / 4
    assert dist["copy_rate"] == 0.5
    assert dist["export_rate"] == 0.5


def test_distribution_ignores_non_publisher_copies(client, db):
    """A user who copies but never publishes must not count — the denominator
    anchors on publishers, same as the north-star."""
    admin = _ensure_admin(db)
    pub = User(openid="dist_pub")
    db.add(pub)
    db.commit()
    db.refresh(pub)
    _emit(db, pub, "publish")

    ghost = User(openid="dist_ghost")
    db.add(ghost)
    db.commit()
    db.refresh(ghost)
    _emit(db, ghost, "copy_to_weibo")  # copied, but never published

    resp = client.get("/api/admin/metrics/funnel", headers=_admin_auth(admin))
    dist = resp.json()["distribution"]
    assert dist["total_publishers"] == 1
    assert dist["copy_users"] == 0
    assert dist["distribution_rate"] == 0.0


def test_distribution_duplicate_copies_count_one_user(client, db):
    admin = _ensure_admin(db)
    u = User(openid="dist_dupe")
    db.add(u)
    db.commit()
    db.refresh(u)
    _emit(db, u, "publish")
    for _ in range(3):
        _emit(db, u, "copy_to_xiaohongshu")

    resp = client.get("/api/admin/metrics/funnel", headers=_admin_auth(admin))
    dist = resp.json()["distribution"]
    assert dist["copy_users"] == 1
    assert dist["distribution_rate"] == 1.0


# ── per-user funnel position ──────────────────────────────────────────────────


def test_user_funnel_position_furthest_step(client, db):
    admin = _ensure_admin(db)
    u = User(openid="positioned", streak=7, points=300)
    db.add(u)
    db.commit()
    db.refresh(u)
    # Reach discuss_round twice; the furthest stage in FUNNEL_STEPS is discuss_round.
    for _ in range(2):
        _emit(db, u, "discuss_round")
    _emit(db, u, "register")

    resp = client.get(
        f"/api/admin/metrics/funnel/user/{u.id}",
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["user_id"] == u.id
    assert body["furthest_step"] == "discuss_round"
    assert body["furthest_step_label"] == "讨论"
    assert body["has_published"] is False
    assert body["last_event"] == "discuss_round"  # most recent
    assert body["current_streak"] == 7
    assert body["points"] == 300


def test_user_funnel_position_no_events(client, db):
    admin = _ensure_admin(db)
    u = User(openid="no_events")
    db.add(u)
    db.commit()
    db.refresh(u)
    resp = client.get(
        f"/api/admin/metrics/funnel/user/{u.id}",
        headers=_admin_auth(admin),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["furthest_step"] is None
    assert body["last_event"] is None
    assert body["has_published"] is False


def test_user_funnel_position_published(client, db):
    admin = _ensure_admin(db)
    u = User(openid="publisher")
    db.add(u)
    db.commit()
    db.refresh(u)
    for ev in ("register", "key_configured", "topic_selected", "publish"):
        _emit(db, u, ev)
    resp = client.get(
        f"/api/admin/metrics/funnel/user/{u.id}",
        headers=_admin_auth(admin),
    )
    body = resp.json()
    assert body["furthest_step"] == "publish"
    assert body["furthest_step_label"] == "发布"
    assert body["has_published"] is True
