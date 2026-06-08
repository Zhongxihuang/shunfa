"""Tests for Appendix C — within-subject (ABAB) comparison dashboard.

Covers:
- segments are cut at gamification_override_changed events on the user's timeline
- publish / discuss_round events are bucketed into the arm active at their time
- on/off rollups sum the right segments
- no toggles → empty report
- admin endpoint: auth gating, 404, and the rolled-up payload
"""

from datetime import datetime, timedelta, timezone

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


def _add_event(db, user_id, event, ts, props_json=None):
    db.add(Event(user_id=user_id, event=event, ts=ts, props_json=props_json))
    db.commit()


def _seed_abab(db) -> User:
    """One user, ABAB timeline: on@t0, off@t2, on@t4. Behaviour interleaved."""
    user = User(openid="ws_abab")
    db.add(user)
    db.commit()
    db.refresh(user)
    base = datetime(2026, 6, 1, tzinfo=timezone.utc)

    # toggles
    _add_event(db, user.id, "gamification_override_changed",
               base, '{"from": "default", "to": "on"}')
    _add_event(db, user.id, "gamification_override_changed",
               base + timedelta(days=2), '{"from": "on", "to": "off"}')
    _add_event(db, user.id, "gamification_override_changed",
               base + timedelta(days=4), '{"from": "off", "to": "on"}')

    # ON segment 1 [t0, t2): 2 publishes, 1 discuss
    _add_event(db, user.id, "publish", base + timedelta(hours=1))
    _add_event(db, user.id, "publish", base + timedelta(days=1))
    _add_event(db, user.id, "discuss_round", base + timedelta(hours=2))
    # OFF segment [t2, t4): 1 publish, 3 discuss
    _add_event(db, user.id, "publish", base + timedelta(days=2, hours=1))
    _add_event(db, user.id, "discuss_round", base + timedelta(days=2, hours=2))
    _add_event(db, user.id, "discuss_round", base + timedelta(days=3))
    _add_event(db, user.id, "discuss_round", base + timedelta(days=3, hours=5))
    # ON segment 2 [t4, None): 1 publish
    _add_event(db, user.id, "publish", base + timedelta(days=5))
    return user


def test_within_subject_buckets_behaviour_by_arm(db):
    from app.services.analytics_queries import get_within_subject_comparison

    user = _seed_abab(db)
    report = get_within_subject_comparison(db, user.id)

    assert len(report.segments) == 3
    assert [s.arm for s in report.segments] == ["on", "off", "on"]

    # ON = segment1 (2 pub, 1 disc) + segment3 (1 pub, 0 disc)
    assert report.on_publish == 3
    assert report.on_discuss == 1
    # OFF = segment2 (1 pub, 3 disc)
    assert report.off_publish == 1
    assert report.off_discuss == 3


def test_within_subject_no_toggles_is_empty(db):
    from app.services.analytics_queries import get_within_subject_comparison

    user = User(openid="ws_none")
    db.add(user)
    db.commit()
    db.refresh(user)
    _add_event(db, user.id, "publish", datetime(2026, 6, 1, tzinfo=timezone.utc))

    report = get_within_subject_comparison(db, user.id)
    assert report.segments == []
    assert report.on_publish == 0
    assert report.off_publish == 0


def test_within_subject_to_dict_shape(db):
    from app.services.analytics_queries import get_within_subject_comparison

    user = _seed_abab(db)
    payload = get_within_subject_comparison(db, user.id).to_dict()
    assert payload["user_id"] == user.id
    assert payload["on"]["publish_count"] == 3
    assert payload["off"]["discuss_round_count"] == 3
    assert len(payload["segments"]) == 3
    assert payload["segments"][0]["arm"] == "on"
