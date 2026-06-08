"""Scripted launch smoke coverage for the Web + backend path."""

from unittest.mock import AsyncMock, patch

from app.models import CheckIn, CheckInStatus, HotTopic, User
from app.utils.time_utils import get_today_cst


async def _fake_quick_generate(**kwargs):
    content = (
        "顺发的价值不是把每句话都润色到完美，而是把选题、起稿、预览和发布压成一条不断点的路径。"
        "先发出去，习惯才有机会发生。"
    )
    return {
        "content": content,
        "platform": kwargs.get("platform", "xiaohongshu"),
        "char_count": len(content),
        "fact_pass": True,
        "fact_issues": [],
        "discussion_pass": True,
        "discussion_issues": [],
    }


async def _fake_confirm_content(checkin, content, db, api_key=""):
    checkin.content = content
    checkin.content_approved = True
    checkin.status = CheckInStatus.pending
    db.commit()
    return {
        "quality_pass": True,
        "quality_issues": [],
        "quality_available": True,
        "fact_pass": True,
        "fact_issues": [],
        "discussion_pass": True,
        "discussion_issues": [],
        "topic": checkin.topic,
    }


async def _fake_compose_assets(checkin, api_key):
    return {
        "pages": ["先发出去，习惯才有机会发生。", "顺发把启动摩擦压进一条闭环路径。"],
        "title": "先发出去",
        "tags": ["顺发", "表达", "习惯", "AI", "发布"],
    }


def test_web_backend_launch_path_register_byok_publish_and_profile(client, db):
    today = get_today_cst()
    db.add(
        HotTopic(
            topic_date=today,
            rank=1,
            title="完美主义让表达变难",
            summary="用户想写但担心不够好，最终反复保存草稿。",
            source="local-smoke",
            url="https://example.com/shunfa-launch-smoke",
            category="product",
            score=9,
            ai_angle="把发出去设计成低摩擦闭环，而不是追求完美文案",
            ai_counter_angle="避免把 AI 写作工具做成更复杂的编辑器",
        )
    )
    db.commit()

    register_response = client.post(
        "/api/register",
        json={"username": "launch_smoke_user", "password": "launch-smoke-password"},
    )
    assert register_response.status_code == 200
    token = register_response.json()["token"]
    headers = {"Authorization": f"Bearer {token}"}

    save_key_response = client.post(
        "/api/user/api_key",
        json={"api_key": "sk-launch-smoke-test-key"},
        headers=headers,
    )
    assert save_key_response.status_code == 200
    save_key_body = save_key_response.json()
    assert save_key_body["configured"] is True
    assert save_key_body["preview"] == "...-key"

    topic_response = client.get("/api/hot_topics/today", headers=headers)
    assert topic_response.status_code == 200
    topic = topic_response.json()["topics"][0]

    select_response = client.post(
        "/api/select_topic",
        json={
            "topic": topic["title"],
            "hot_topic_id": topic["id"],
            "selected_angle": topic["ai_angle"],
            "platform": "xiaohongshu",
        },
        headers=headers,
    )
    assert select_response.status_code == 200
    checkin_id = select_response.json()["checkin_id"]

    with (
        patch(
            "app.services.generation_orchestrator.quick_generate",
            new=AsyncMock(side_effect=_fake_quick_generate),
        ),
        patch(
            "app.routers.content.confirm_content",
            new=AsyncMock(side_effect=_fake_confirm_content),
        ),
        patch(
            "app.routers.content.compose_post_assets",
            new=AsyncMock(side_effect=_fake_compose_assets),
        ),
    ):
        quick_response = client.post(
            "/api/quick_generate",
            json={
                "topic_id": topic["id"],
                "checkin_id": checkin_id,
                "hot_topic": topic["title"],
                "angle": topic["ai_angle"],
                "platform": "xiaohongshu",
            },
            headers=headers,
        )
        assert quick_response.status_code == 200
        draft = quick_response.json()["content"]

        preview_response = client.post(
            "/api/confirm_content",
            json={"checkin_id": checkin_id, "content": draft},
            headers=headers,
        )
        assert preview_response.status_code == 200
        assert preview_response.json()["status"] == "pending"

        compose_response = client.post(
            "/api/compose_post_assets",
            json={"checkin_id": checkin_id, "template": "beige"},
            headers=headers,
        )
        assert compose_response.status_code == 200
        assert len(compose_response.json()["pages"]) == 2

        publish_response = client.post(
            "/api/confirm_publish",
            json={"checkin_id": checkin_id},
            headers=headers,
        )
        assert publish_response.status_code == 200
        published = publish_response.json()
        assert published["points_earned"] > 0
        assert published["streak"] == 1

        duplicate_response = client.post(
            "/api/confirm_publish",
            json={"checkin_id": checkin_id},
            headers=headers,
        )
        assert duplicate_response.status_code == 409

    status_response = client.get("/api/user_status", headers=headers)
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["today_completed"] is True
    assert status["streak"] == published["streak"]
    assert status["points"] == published["total_points"]

    profile_response = client.get("/api/my/checkins", headers=headers)
    assert profile_response.status_code == 200
    history = profile_response.json()
    assert history["total"] == 1
    assert history["checkins"][0]["status"] == "completed"
    assert history["checkins"][0]["points_earned"] == published["points_earned"]

    user = db.query(User).filter(User.username == "launch_smoke_user").one()
    checkin = db.query(CheckIn).filter(CheckIn.id == checkin_id).one()
    assert user.points == published["total_points"]
    assert user.streak == 1
    assert checkin.status == CheckInStatus.completed
    assert checkin.points_earned == published["points_earned"]
