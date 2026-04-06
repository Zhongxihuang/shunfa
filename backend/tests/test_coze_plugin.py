"""Tests for Coze plugin endpoints."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.models import User, CheckIn, CheckInStatus
from app.utils.time_utils import get_today_cst

PLUGIN_TOKEN = "shunfa-coze-token"
FEISHU_USER_ID = "feishu_test_user_001"

COZE_HEADERS = {
    "X-Coze-Plugin-Token": PLUGIN_TOKEN,
    "X-Feishu-User-Id": FEISHU_USER_ID,
}


def _create_feishu_user(db) -> User:
    user = User(openid=f"feishu:{FEISHU_USER_ID}", streak=3, points=150, level=2)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ── Auth ──────────────────────────────────────────────────────────────────────

def test_coze_endpoint_requires_plugin_token(client):
    response = client.get(
        "/api/coze/user_stats",
        headers={"X-Feishu-User-Id": FEISHU_USER_ID},
    )
    assert response.status_code == 422  # missing required header


def test_coze_endpoint_rejects_wrong_token(client):
    response = client.get(
        "/api/coze/user_stats",
        headers={
            "X-Coze-Plugin-Token": "wrong-token",
            "X-Feishu-User-Id": FEISHU_USER_ID,
        },
    )
    assert response.status_code == 401


def test_coze_creates_user_on_first_call(client, db):
    response = client.get("/api/coze/user_stats", headers=COZE_HEADERS)
    assert response.status_code == 200
    # User should have been auto-created
    user = db.query(User).filter(User.openid == f"feishu:{FEISHU_USER_ID}").first()
    assert user is not None


# ── get_hot_topics ────────────────────────────────────────────────────────────

def test_get_hot_topics_returns_list(client, db):
    _create_feishu_user(db)

    mock_topics = [
        MagicMock(
            hot_topic="DeepSeek V4发布",
            hot_source="Hacker News",
            ai_angle="国产AI性价比之战",
            ai_counter_angle="成本不等于质量",
            score=8,
            topic_category=MagicMock(value="ai_model"),
            record_id="rec_001",
        )
    ]

    with patch("app.routers.coze_plugin.get_pending_topics", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_topics
        response = client.get("/api/coze/get_hot_topics", headers=COZE_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert len(data["topics"]) == 1
    assert data["topics"][0]["hot_topic"] == "DeepSeek V4发布"
    assert data["topics"][0]["index"] == 1
    assert "date" in data


def test_get_hot_topics_handles_bitable_error(client, db):
    _create_feishu_user(db)

    with patch("app.routers.coze_plugin.get_pending_topics", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = Exception("Bitable unavailable")
        response = client.get("/api/coze/get_hot_topics", headers=COZE_HEADERS)

    # Should return empty list gracefully
    assert response.status_code == 200
    assert response.json()["topics"] == []


# ── quick_generate ────────────────────────────────────────────────────────────

def test_coze_quick_generate(client, db):
    _create_feishu_user(db)

    with patch("app.routers.coze_plugin.quick_generate", new_callable=AsyncMock) as mock_qg:
        mock_qg.return_value = {
            "content": "生成的内容",
            "platform": "xiaohongshu",
            "char_count": 6,
        }
        response = client.post(
            "/api/coze/quick_generate",
            json={
                "hot_topic": "DeepSeek V4",
                "angle": "国产AI性价比",
                "platform": "xiaohongshu",
            },
            headers=COZE_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["content"] == "生成的内容"
    assert data["platform"] == "xiaohongshu"


# ── start_deep_mode ───────────────────────────────────────────────────────────

def test_start_deep_mode_creates_checkin(client, db):
    _create_feishu_user(db)

    with patch("app.routers.coze_plugin.process_message", new_callable=AsyncMock) as mock_pm:
        mock_pm.return_value = {
            "reply": "好，这个热点可以从3个角度聊...",
            "status": CheckInStatus.discussing,
            "draft": None,
        }
        response = client.post(
            "/api/coze/start_deep_mode",
            json={
                "hot_topic": "DeepSeek V4发布",
                "angle": "国产AI性价比之战",
            },
            headers=COZE_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert "checkin_id" in data
    assert data["checkin_id"] > 0
    assert "opening_message" in data

    # Verify CheckIn was created in DB
    user = db.query(User).filter(User.openid == f"feishu:{FEISHU_USER_ID}").first()
    checkin = db.query(CheckIn).filter(CheckIn.user_id == user.id).first()
    assert checkin is not None
    assert checkin.topic == "DeepSeek V4发布"


def test_start_deep_mode_reuses_existing_checkin(client, db):
    user = _create_feishu_user(db)
    today = get_today_cst()
    existing = CheckIn(
        user_id=user.id,
        date=today,
        topic="Old topic",
        status=CheckInStatus.discussing,
    )
    db.add(existing)
    db.commit()

    with patch("app.routers.coze_plugin.process_message", new_callable=AsyncMock) as mock_pm:
        mock_pm.return_value = {"reply": "角度建议...", "status": CheckInStatus.discussing, "draft": None}
        response = client.post(
            "/api/coze/start_deep_mode",
            json={"hot_topic": "New hot topic", "angle": "角度"},
            headers=COZE_HEADERS,
        )

    assert response.status_code == 200
    # Should still only be one checkin
    checkins = db.query(CheckIn).filter(CheckIn.user_id == user.id).all()
    assert len(checkins) == 1
    # Topic updated to new one
    db.refresh(checkins[0])
    assert checkins[0].topic == "New hot topic"


# ── deep_mode_message ─────────────────────────────────────────────────────────

def test_deep_mode_message_returns_reply(client, db):
    user = _create_feishu_user(db)
    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="DeepSeek V4",
        status=CheckInStatus.discussing,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    with patch("app.routers.coze_plugin.process_message", new_callable=AsyncMock) as mock_pm:
        mock_pm.return_value = {
            "reply": "好的，我帮你整理了初稿",
            "status": CheckInStatus.draft_ready,
            "draft": "生成的初稿内容",
        }
        response = client.post(
            "/api/coze/deep_mode_message",
            json={"checkin_id": checkin.id, "message": "1", "angle": "性价比角度"},
            headers=COZE_HEADERS,
        )

    assert response.status_code == 200
    data = response.json()
    assert data["has_draft"] is True
    assert data["draft"] == "生成的初稿内容"
    assert data["status"] == "draft_ready"


def test_deep_mode_message_404_for_wrong_user(client, db):
    user = _create_feishu_user(db)
    other_user = User(openid="feishu:other_user")
    db.add(other_user)
    db.commit()
    db.refresh(other_user)

    checkin = CheckIn(
        user_id=other_user.id,
        date=get_today_cst(),
        topic="Other user topic",
        status=CheckInStatus.discussing,
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    response = client.post(
        "/api/coze/deep_mode_message",
        json={"checkin_id": checkin.id, "message": "hello"},
        headers=COZE_HEADERS,
    )
    assert response.status_code == 404


# ── confirm_and_publish ───────────────────────────────────────────────────────

def test_confirm_and_publish_returns_streak(client, db):
    user = _create_feishu_user(db)
    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="DeepSeek V4",
        status=CheckInStatus.draft_ready,
        content="初稿内容",
    )
    db.add(checkin)
    db.commit()
    db.refresh(checkin)

    with patch("app.routers.coze_plugin.confirm_content", new_callable=AsyncMock) as mock_cc:
        mock_cc.return_value = {"quality_pass": True, "quality_issues": [], "topic": "DeepSeek V4"}
        with patch("app.routers.coze_plugin.confirm_publish", new_callable=AsyncMock) as mock_cp:
            mock_cp.return_value = {
                "streak": 4,
                "points_earned": 45,
                "total_points": 195,
                "level": 2,
                "diamonds": 4,
                "message": "继续保持！已连更4天",
                "newly_unlocked": [],
            }
            response = client.post(
                "/api/coze/confirm_and_publish",
                json={"checkin_id": checkin.id, "content": "最终发布内容"},
                headers=COZE_HEADERS,
            )

    assert response.status_code == 200
    data = response.json()
    assert data["streak"] == 4
    assert data["points_earned"] == 45
    assert "message" in data


# ── user_stats ────────────────────────────────────────────────────────────────

def test_get_user_stats(client, db):
    user = _create_feishu_user(db)

    response = client.get("/api/coze/user_stats", headers=COZE_HEADERS)

    assert response.status_code == 200
    data = response.json()
    assert data["streak"] == 3
    assert data["points"] == 150
    assert data["level"] == 2
    assert data["today_completed"] is False


def test_get_user_stats_today_completed(client, db):
    user = _create_feishu_user(db)
    checkin = CheckIn(
        user_id=user.id,
        date=get_today_cst(),
        topic="Topic",
        status=CheckInStatus.completed,
    )
    db.add(checkin)
    db.commit()

    response = client.get("/api/coze/user_stats", headers=COZE_HEADERS)
    assert response.status_code == 200
    assert response.json()["today_completed"] is True
