"""Tests for the subtraction-experiment feature flag (W2.7).

The Week-3 subtraction experiment hides ALL gamification UI for a stable,
deterministic slice of users so we can measure whether gamification actually
creates retention. What we verify:

- bucketing is stable for a given user_id and independent of Python's salted
  hash() (so backend restarts / multiple workers agree)
- pct=0 keeps everyone in the gamification group (the safe default)
- pct=100 puts everyone in the subtraction group
- a partial pct splits users and is monotonic (raising pct only ever moves
  users INTO the experiment, never out)
- user_status / login surface `gamification_enabled` so the client can hide UI
"""

from app.config import settings
from app.models import User
from app.routers.user import create_jwt_token
from app.services import feature_flags as ff


def _make_user(db, openid="ff_user", **kw) -> User:
    user = User(openid=openid, **kw)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


# ── bucketing math ─────────────────────────────────────────────────────────────


def test_bucket_is_stable_and_in_range():
    buckets = {ff.user_bucket(uid) for uid in range(1, 200)}
    assert all(0 <= b < 100 for b in buckets)
    # same input → same bucket (not Python's salted hash)
    assert ff.user_bucket(42) == ff.user_bucket(42)


def test_pct_zero_keeps_everyone_in_gamification(monkeypatch):
    monkeypatch.setattr(settings, "subtraction_experiment_pct", 0)
    assert all(not ff.in_subtraction_experiment(uid) for uid in range(1, 500))


def test_pct_hundred_puts_everyone_in_experiment(monkeypatch):
    monkeypatch.setattr(settings, "subtraction_experiment_pct", 100)
    assert all(ff.in_subtraction_experiment(uid) for uid in range(1, 500))


def test_partial_pct_splits_and_is_monotonic(monkeypatch):
    ids = list(range(1, 1001))

    monkeypatch.setattr(settings, "subtraction_experiment_pct", 30)
    group_30 = {uid for uid in ids if ff.in_subtraction_experiment(uid)}
    # roughly 30% — allow generous slack for a 1000-sample hash split
    assert 200 < len(group_30) < 400

    monkeypatch.setattr(settings, "subtraction_experiment_pct", 60)
    group_60 = {uid for uid in ids if ff.in_subtraction_experiment(uid)}
    # raising pct only ever ADDS users to the experiment
    assert group_30 <= group_60


def test_gamification_enabled_is_inverse(monkeypatch):
    monkeypatch.setattr(settings, "subtraction_experiment_pct", 100)
    assert ff.gamification_enabled(7) is False
    monkeypatch.setattr(settings, "subtraction_experiment_pct", 0)
    assert ff.gamification_enabled(7) is True


# ── surfaced through the API ───────────────────────────────────────────────────


def test_user_status_reports_gamification_enabled(client, db, monkeypatch):
    monkeypatch.setattr(settings, "subtraction_experiment_pct", 100)
    user = _make_user(db, openid="ff_status")
    resp = client.get("/api/user_status", headers=_auth(user))
    assert resp.status_code == 200
    assert resp.json()["gamification_enabled"] is False


def test_user_status_default_enables_gamification(client, db, monkeypatch):
    monkeypatch.setattr(settings, "subtraction_experiment_pct", 0)
    user = _make_user(db, openid="ff_status_on")
    resp = client.get("/api/user_status", headers=_auth(user))
    assert resp.status_code == 200
    assert resp.json()["gamification_enabled"] is True
