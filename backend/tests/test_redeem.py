"""Tests for the diamond sink / 积分钻石出口 (W3.9).

Diamonds used to be a dead number: `user.diamonds` was recomputed as
`3 + points//100` on every publish, so there was nothing to spend them on and
no way to spend them. We add a persistent `diamonds_spent` ledger so the
effective balance = earned − spent, and a redemption endpoint with at least one
real sink: buying a streak-freeze card.

What we verify:
- the effective-balance math (earned − spent) survives a re-derivation
- redeeming a freeze card costs diamonds AND grants a card
- insufficient balance is rejected and changes nothing
- an unknown item is rejected
- a redemption emits a `redeem` event for measurement
"""

from app.models import Event, User
from app.routers.user import create_jwt_token
from app.services import redeem_service as rs
from app.services.points_service import apply_points_and_update_user


def _make_user(db, **kw) -> User:
    user = User(openid=kw.pop("openid", "redeem_user"), **kw)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


# ── effective-balance math ─────────────────────────────────────────────────────


def test_effective_balance_subtracts_spent(db):
    # 1000 points → earned = 3 + 10 = 13 diamonds
    user = _make_user(db, points=1000, diamonds=13, diamonds_spent=5)
    assert rs.effective_diamonds(user) == 8


def test_spent_persists_across_points_rederivation(db):
    """Re-applying points must NOT wipe out diamonds the user already spent."""
    from app.models import CheckIn
    from app.utils.time_utils import get_today_cst

    user = _make_user(db, points=1000, diamonds_spent=5, streak=1)
    checkin = CheckIn(user_id=user.id, date=get_today_cst(), topic="t")
    db.add(checkin)
    db.commit()
    apply_points_and_update_user(user, checkin, db)
    db.commit()
    db.refresh(user)
    # earned grew (points went up) but the 5 already-spent are still gone
    assert user.diamonds == rs.diamonds_earned(user.points) - 5


# ── redemption ─────────────────────────────────────────────────────────────────


def test_redeem_streak_freeze_spends_and_grants(db):
    user = _make_user(db, points=1000, diamonds=13, streak_freezes=0)
    result = rs.redeem(db, user, "streak_freeze")
    cost = rs.CATALOG["streak_freeze"]["cost"]
    assert user.streak_freezes == 1
    assert user.diamonds == 13 - cost
    assert result["diamonds"] == 13 - cost
    assert result["streak_freezes"] == 1
    assert len(db.query(Event).filter(Event.event == "redeem").all()) == 1


def test_redeem_insufficient_balance_rejected(db):
    user = _make_user(db, points=0, diamonds=3, streak_freezes=0)
    # earned = 3, spend most of it first so a freeze is unaffordable
    user.diamonds_spent = 2  # effective = 1
    db.commit()
    try:
        rs.redeem(db, user, "streak_freeze")
        raise AssertionError("expected redemption to be rejected")
    except rs.RedeemError as exc:
        assert exc.code == "insufficient_diamonds"
    db.refresh(user)
    assert user.streak_freezes == 0  # nothing granted


def test_redeem_unknown_item_rejected(db):
    user = _make_user(db, points=1000, diamonds=13)
    try:
        rs.redeem(db, user, "no_such_item")
        raise AssertionError("expected unknown item to be rejected")
    except rs.RedeemError as exc:
        assert exc.code == "unknown_item"


# ── through the endpoint ────────────────────────────────────────────────────────


def test_redeem_endpoint_happy_path(client, db):
    user = _make_user(db, openid="redeem_api", points=1000, diamonds=13, streak_freezes=0)
    resp = client.post("/api/redeem", json={"item": "streak_freeze"}, headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["streak_freezes"] == 1
    assert body["diamonds"] == 13 - rs.CATALOG["streak_freeze"]["cost"]


def test_redeem_endpoint_insufficient_returns_400(client, db):
    user = _make_user(db, openid="redeem_api_poor", points=0, diamonds=3)
    user.diamonds_spent = 3  # effective balance 0
    db.commit()
    resp = client.post("/api/redeem", json={"item": "streak_freeze"}, headers=_auth(user))
    assert resp.status_code == 400
    assert resp.json()["error_code"] == "insufficient_diamonds"
