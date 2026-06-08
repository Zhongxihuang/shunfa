"""Cohort segmentation for the subtraction experiment (W3.10).

The subtraction experiment hides gamification from a deterministic md5-bucketed
slice of users. To "read the data and decide" you must compare the two arms —
control (gamification ON) vs subtraction (gamification OFF) — on the same funnel
and north-star metrics. A global funnel that mixes both arms cannot answer
"did removing gamification help or hurt", so the queries must accept a cohort.

The cohort is a pure function of user_id (`in_subtraction_experiment`), so these
tests partition users by monkeypatching that predicate to a known id set.
"""

from app.models import Event, User
from app.services import analytics_queries
from app.services.analytics_queries import get_funnel, get_north_star


def _emit(db, user, event):
    db.add(Event(user_id=user.id, event=event, props_json=None))
    db.commit()


def _full_funnel(db, openid, streak=0):
    user = User(openid=openid, streak=streak)
    db.add(user)
    db.commit()
    db.refresh(user)
    for ev in (
        "register",
        "key_configured",
        "topic_selected",
        "discuss_round",
        "draft_generated",
        "publish",
    ):
        _emit(db, user, ev)
    return user


def test_funnel_cohort_partitions_users(db, monkeypatch):
    """control vs subtraction funnels must count only their own arm's users."""
    a = _full_funnel(db, "arm_sub_1")
    b = _full_funnel(db, "arm_sub_2")
    c = _full_funnel(db, "arm_ctrl_1")

    subtraction_ids = {a.id, b.id}
    monkeypatch.setattr(
        analytics_queries,
        "in_subtraction_experiment",
        lambda uid: uid in subtraction_ids,
        raising=False,
    )

    sub = {s.event: s.users for s in get_funnel(db, cohort="subtraction").steps}
    ctrl = {s.event: s.users for s in get_funnel(db, cohort="control").steps}
    everyone = {s.event: s.users for s in get_funnel(db).steps}

    assert sub["register"] == 2
    assert sub["publish"] == 2
    assert ctrl["register"] == 1
    assert ctrl["publish"] == 1
    # No cohort = both arms combined.
    assert everyone["register"] == 3
    assert everyone["publish"] == 3
    # c is in control only.
    assert c.id not in subtraction_ids


def test_north_star_cohort_partitions_publishers(db, monkeypatch):
    """North-star ratio must be computable per arm."""
    a = _full_funnel(db, "ns_sub_hooked", streak=5)  # subtraction, qualifies
    b = _full_funnel(db, "ns_sub_cold", streak=1)  # subtraction, does not qualify
    c = _full_funnel(db, "ns_ctrl_hooked", streak=4)  # control, qualifies

    subtraction_ids = {a.id, b.id}
    monkeypatch.setattr(
        analytics_queries,
        "in_subtraction_experiment",
        lambda uid: uid in subtraction_ids,
        raising=False,
    )

    sub = get_north_star(db, cohort="subtraction")
    ctrl = get_north_star(db, cohort="control")

    # Subtraction arm: 2 publishers, 1 qualifies → 0.5
    assert sub.total_users == 2
    assert sub.qualifying_users == 1
    assert sub.ratio == 0.5

    # Control arm: 1 publisher, 1 qualifies → 1.0
    assert ctrl.total_users == 1
    assert ctrl.qualifying_users == 1
    assert ctrl.ratio == 1.0
    assert c.id not in subtraction_ids


def _admin_headers(db):
    from app.routers.user import create_jwt_token

    admin = db.query(User).filter(User.openid == "web_admin").first()
    if not admin:
        admin = User(openid="web_admin")
        db.add(admin)
        db.commit()
        db.refresh(admin)
    return {"Authorization": f"Bearer {create_jwt_token(admin.id)}"}


def test_funnel_endpoint_accepts_cohort_param(client, db):
    """The admin endpoint exposes ?cohort= and echoes it back."""
    resp = client.get(
        "/api/admin/metrics/funnel?cohort=subtraction", headers=_admin_headers(db)
    )
    assert resp.status_code == 200
    assert resp.json()["cohort"] == "subtraction"


def test_funnel_endpoint_rejects_bad_cohort(client, db):
    resp = client.get(
        "/api/admin/metrics/funnel?cohort=banana", headers=_admin_headers(db)
    )
    assert resp.status_code == 422


def test_cohort_none_matches_unfiltered(db):
    """Passing cohort=None must equal the legacy unfiltered behaviour."""
    _full_funnel(db, "plain_1")
    _full_funnel(db, "plain_2")
    none_steps = {s.event: s.users for s in get_funnel(db, cohort=None).steps}
    legacy_steps = {s.event: s.users for s in get_funnel(db).steps}
    assert none_steps == legacy_steps
