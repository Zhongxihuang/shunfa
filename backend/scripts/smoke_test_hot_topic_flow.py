"""Local smoke test for the Web hot-topic writing flow.

Usage:
    cd backend && python -m scripts.smoke_test_hot_topic_flow

This script validates the current product path:
1. local hot topic read endpoint returns a topic
2. select_topic creates a checkin
3. quick_generate persists draft content
4. confirm_content produces publish guidance
5. compose_post_assets returns image pages + title + tags
6. confirm_publish completes the checkin

The AI-heavy steps are mocked so this smoke test verifies routing, auth, DB state
transitions, and response contracts without depending on external providers.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.main import app
from app.models import CheckIn, CheckInStatus, HotTopic, User
from app.routers.user import create_jwt_token
from app.utils.time_utils import get_today_cst


def ensure_smoke_user_and_topic() -> tuple[str, int]:
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.openid == "local_hot_topic_smoke_user").first()
        if user is None:
            user = User(openid="local_hot_topic_smoke_user")
            db.add(user)
            db.commit()
            db.refresh(user)

        today = get_today_cst()
        db.query(CheckIn).filter(
            CheckIn.user_id == user.id,
            CheckIn.date == today,
        ).delete()
        db.commit()

        topic = db.query(HotTopic).filter(
            HotTopic.topic_date == today,
            HotTopic.title == "本地热点链路烟测",
        ).first()
        if topic is None:
            topic = HotTopic(
                topic_date=today,
                rank=1,
                title="本地热点链路烟测",
                summary="用于验证本地热点到图文素材再到打卡的主链路。",
                source="local-smoke",
                url="https://example.com/local-smoke",
                category="tech",
                score=9,
                ai_angle="用明确观点解释本地热点链路为什么更稳定",
                ai_counter_angle="提醒不要把链路收敛误解为功能变少",
            )
            db.add(topic)
            db.commit()
            db.refresh(topic)

        return create_jwt_token(user.id), topic.id
    finally:
        db.close()


async def fake_quick_generate(**kwargs):
    return {
        "content": "本地热点链路已经收敛，读路径只依赖本地表，刷新失败时也不会影响已有热点展示。",
        "platform": kwargs.get("platform", "xiaohongshu"),
        "char_count": 38,
        "fact_pass": True,
        "fact_issues": [],
        "discussion_pass": True,
        "discussion_issues": [],
    }


async def fake_confirm_content(checkin, content, db, api_key=""):
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


async def fake_compose_assets(checkin, api_key):
    return {
        "pages": ["第一页：链路收敛。", "第二页：刷新和读取解耦。"],
        "title": "🔥 热点链路更稳了",
        "tags": ["顺发", "热点", "AI", "图文", "打卡"],
    }


def main() -> None:
    token, topic_id = ensure_smoke_user_and_topic()
    headers = {"Authorization": f"Bearer {token}"}

    with TestClient(app) as client:
        with (
            patch("app.routers.content.quick_generate", new=AsyncMock(side_effect=fake_quick_generate)),
            patch("app.routers.content.confirm_content", new=AsyncMock(side_effect=fake_confirm_content)),
            patch("app.routers.content.compose_post_assets", new=AsyncMock(side_effect=fake_compose_assets)),
        ):
            hot_topics_response = client.get("/api/hot_topics/today", headers=headers)
            hot_topics_response.raise_for_status()
            hot_topics = hot_topics_response.json()["topics"]
            if not hot_topics:
                raise RuntimeError("No local hot topics available")

            selected_topic = next((t for t in hot_topics if t["id"] == topic_id), hot_topics[0])
            select_response = client.post(
                "/api/select_topic",
                json={
                    "topic": selected_topic["title"],
                    "hot_topic_id": selected_topic["id"],
                    "selected_angle": selected_topic["ai_angle"],
                    "platform": "xiaohongshu",
                },
                headers=headers,
            )
            select_response.raise_for_status()
            checkin_id = select_response.json()["checkin_id"]

            quick_response = client.post(
                "/api/quick_generate",
                json={
                    "topic_id": selected_topic["id"],
                    "checkin_id": checkin_id,
                    "hot_topic": selected_topic["title"],
                    "angle": selected_topic["ai_angle"],
                    "platform": "xiaohongshu",
                },
                headers=headers,
            )
            quick_response.raise_for_status()
            draft = quick_response.json()["content"]

            confirm_response = client.post(
                "/api/confirm_content",
                json={"checkin_id": checkin_id, "content": draft},
                headers=headers,
            )
            confirm_response.raise_for_status()

            compose_response = client.post(
                "/api/compose_post_assets",
                json={"checkin_id": checkin_id, "template": "beige", "regenerate": False},
                headers=headers,
            )
            compose_response.raise_for_status()

            publish_response = client.post(
                "/api/confirm_publish",
                json={"checkin_id": checkin_id},
                headers=headers,
            )
            publish_response.raise_for_status()

    print(
        json.dumps(
            {
                "hot_topics_count": len(hot_topics),
                "selected_topic": selected_topic["title"],
                "checkin_id": checkin_id,
                "quality_approved": confirm_response.json()["content_approved"],
                "asset_pages": len(compose_response.json()["pages"]),
                "asset_tags": len(compose_response.json()["tags"]),
                "publish_points": publish_response.json()["points_earned"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
