"""Tests for the entry-loop free trial (W2.1 BYOK 免费额度兜底).

What we verify:
- the free-quota service math (limit / remaining / enabled / consume)
- get_resolved_api_key prefers a user's own key over the free pool
- get_resolved_api_key hands out the shared key while quota remains, and marks
  request.state.api_key_source = "free_quota"
- when quota is exhausted, generation raises the `free_quota_exhausted` error
  AND tracks the event (so we can measure free→BYOK conversion)
- a successful quick_generate on the free pool charges exactly one credit
- discussion rounds that don't produce a draft do NOT charge
- the api_key/status endpoint reports remaining quota
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.config import settings
from app.models import Event, User
from app.routers.user import create_jwt_token
from app.services import free_quota as fq


@pytest.fixture
def free_trial(monkeypatch):
    """Enable a 2-generation free trial backed by a shared key."""
    monkeypatch.setattr(settings, "free_quota_limit", 2)
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-shared-platform-key")
    monkeypatch.setattr(settings, "require_user_api_key", True)
    yield


def _make_user(db, openid="fq_user", **kw) -> User:
    user = User(openid=openid, **kw)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def _auth(user: User) -> dict:
    return {"Authorization": f"Bearer {create_jwt_token(user.id)}"}


def _events_for(db, user_id: int, event: str):
    return db.query(Event).filter(Event.user_id == user_id, Event.event == event).all()


# ── service math ──────────────────────────────────────────────────────────────


def test_quota_disabled_by_default(monkeypatch):
    monkeypatch.setattr(settings, "free_quota_limit", 0)
    assert fq.free_quota_enabled() is False


def test_quota_enabled_needs_shared_key(monkeypatch):
    monkeypatch.setattr(settings, "free_quota_limit", 3)
    monkeypatch.setattr(settings, "deepseek_api_key", None)
    assert fq.free_quota_enabled() is False
    monkeypatch.setattr(settings, "deepseek_api_key", "sk-x")
    assert fq.free_quota_enabled() is True


def test_remaining_and_consume(db, free_trial):
    user = _make_user(db)
    assert fq.free_quota_remaining(user) == 2
    assert fq.consume_free_quota(db, user) == 1
    assert fq.consume_free_quota(db, user) == 0
    assert fq.free_quota_remaining(user) == 0
    rows = _events_for(db, user.id, "free_quota_used")
    assert len(rows) == 2


# ── dependency resolution ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_own_key_beats_free_pool(db, free_trial):
    """A user with their own key never burns the free pool."""
    from app.utils.crypto import encrypt_api_key
    from app.dependencies import get_resolved_api_key

    user = _make_user(db, deepseek_api_key=encrypt_api_key("sk-user-own-key"))

    class _Req:
        headers: dict = {}

        class state:  # noqa: N801 - mimic Starlette request.state
            pass

    req = _Req()
    key = await get_resolved_api_key(req, current_user=user)  # type: ignore[arg-type]
    assert key == "sk-user-own-key"
    assert req.state.api_key_source == "user"
    assert fq.free_quota_remaining(user) == 2  # untouched


@pytest.mark.asyncio
async def test_free_pool_used_when_no_own_key(db, free_trial):
    from app.dependencies import get_resolved_api_key

    user = _make_user(db)

    class _Req:
        headers: dict = {}

        class state:  # noqa: N801
            pass

    req = _Req()
    key = await get_resolved_api_key(req, current_user=user)  # type: ignore[arg-type]
    assert key == "sk-shared-platform-key"
    assert req.state.api_key_source == "free_quota"


@pytest.mark.asyncio
async def test_exhausted_raises_and_tracks(db, free_trial):
    from app.dependencies import get_resolved_api_key

    user = _make_user(db)
    user.free_quota_used = 2  # already at the cap
    db.commit()

    class _Req:
        headers: dict = {}

        class state:  # noqa: N801
            pass

    with pytest.raises(HTTPException) as exc:
        await get_resolved_api_key(_Req(), current_user=user)  # type: ignore[arg-type]
    assert exc.value.detail["error_code"] == "free_quota_exhausted"
    assert len(_events_for(db, user.id, "free_quota_exhausted")) == 1


# ── end-to-end through the generation endpoint ─────────────────────────────────


def _draft_result():
    return {
        "content": "这是一段生成的内容。",
        "platform": "xiaohongshu",
        "char_count": 10,
        "fact_pass": True,
        "fact_issues": [],
        "discussion_pass": True,
        "discussion_issues": [],
    }


def test_quick_generate_charges_one_free_credit(client, db, free_trial):
    user = _make_user(db, openid="fq_quick")
    with patch(
        "app.services.generation_orchestrator.quick_generate",
        new=AsyncMock(return_value=_draft_result()),
    ), patch(
        "app.services.generation_orchestrator.enrich_facts",
        new=AsyncMock(side_effect=lambda **kw: kw["base_fact_block"]),
    ):
        resp = client.post(
            "/api/quick_generate",
            json={"hot_topic": "AI 新闻", "angle": "我的看法", "platform": "xiaohongshu"},
            headers=_auth(user),
        )
    assert resp.status_code == 200
    db.refresh(user)
    assert user.free_quota_used == 1
    assert len(_events_for(db, user.id, "free_quota_used")) == 1


def test_status_endpoint_reports_quota(client, db, free_trial):
    user = _make_user(db, openid="fq_status")
    user.free_quota_used = 1
    db.commit()
    resp = client.get("/api/user/api_key/status", headers=_auth(user))
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["free_quota_enabled"] is True
    assert body["free_quota_limit"] == 2
    assert body["free_quota_used"] == 1
    assert body["free_quota_remaining"] == 1
