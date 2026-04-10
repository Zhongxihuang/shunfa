"""Read-only smoke test for Coze plugin + Feishu Bitable wiring.

Usage:
    cd backend && python scripts/smoke_test_coze_feishu_flow.py

This script does not mutate Bitable data.
It does write local sqlite checkin rows through the plugin workflow.
It validates:
1. required env vars are present
2. Feishu tenant token can be fetched
3. hot-topic table fields can be listed
4. pending topics can be fetched from Bitable
5. local Coze plugin endpoint returns the same structure
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.clients.bitable_client import get_bitable_client
from app.services.hot_topic_store import get_pending_topics


REQUIRED_SETTINGS = {
    "coze_plugin_token": settings.coze_plugin_token,
    "feishu_app_id": settings.feishu_app_id,
    "feishu_app_secret": settings.feishu_app_secret,
    "feishu_bitable_app_token": settings.feishu_bitable_app_token,
    "bitable_hot_topic_table_id": settings.bitable_hot_topic_table_id,
}


def validate_settings() -> None:
    missing = [name for name, value in REQUIRED_SETTINGS.items() if not value]
    if missing:
        raise RuntimeError(f"Missing required settings: {', '.join(missing)}")


async def live_bitable_checks() -> dict:
    client = get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id

    fields = await client.list_fields(table_id)
    pending_topics = await get_pending_topics(limit=3, client=client)

    return {
        "field_count": len(fields),
        "field_names": [f.get("field_name", "") for f in fields[:10]],
        "pending_count": len(pending_topics),
        "non_empty_hot_url_count": sum(1 for topic in pending_topics if topic.hot_url),
        "sample_topics": [
            {
                "hot_topic": topic.hot_topic,
                "hot_source": topic.hot_source,
                "hot_url": topic.hot_url,
                "score": topic.score,
            }
            for topic in pending_topics
        ],
    }


def local_plugin_check() -> dict:
    with TestClient(app) as client:
        hot_topics_response = client.get(
            "/api/coze/get_hot_topics?limit=3",
            headers={
                "X-Feishu-User-Id": "smoke-test-user",
                "X-Coze-Plugin-Token": settings.coze_plugin_token,
            },
        )

        if hot_topics_response.status_code != 200:
            raise RuntimeError(
                f"Local plugin endpoint failed: {hot_topics_response.status_code} {hot_topics_response.text}"
            )

        payload = hot_topics_response.json()
        topics = payload.get("topics", [])
        if not topics:
            raise RuntimeError("No topics available from local plugin endpoint")

        first = topics[0]
        topic = first["hot_topic"]
        angle = first.get("ai_angle") or "从行业视角给出一个明确判断"

        quick_response = client.post(
            "/api/coze/quick_generate",
            json={"hot_topic": topic, "angle": angle, "platform": "xiaohongshu"},
            headers={
                "X-Feishu-User-Id": "smoke-test-user",
                "X-Coze-Plugin-Token": settings.coze_plugin_token,
            },
        )
        if quick_response.status_code != 200:
            raise RuntimeError(
                f"Local quick_generate failed: {quick_response.status_code} {quick_response.text}"
            )
        quick_payload = quick_response.json()

        start_response = client.post(
            "/api/coze/start_deep_mode",
            json={"hot_topic": topic, "angle": angle},
            headers={
                "X-Feishu-User-Id": "smoke-test-user",
                "X-Coze-Plugin-Token": settings.coze_plugin_token,
            },
        )
        if start_response.status_code != 200:
            raise RuntimeError(
                f"Local start_deep_mode failed: {start_response.status_code} {start_response.text}"
            )
        start_payload = start_response.json()

        message_response = client.post(
            "/api/coze/deep_mode_message",
            json={
                "checkin_id": start_payload["checkin_id"],
                "message": "1",
                "angle": angle,
            },
            headers={
                "X-Feishu-User-Id": "smoke-test-user",
                "X-Coze-Plugin-Token": settings.coze_plugin_token,
            },
        )
        if message_response.status_code != 200:
            raise RuntimeError(
                f"Local deep_mode_message failed: {message_response.status_code} {message_response.text}"
            )
        message_payload = message_response.json()

        publish_content = message_payload.get("draft") or quick_payload.get("content") or "烟测占位内容"
        publish_response = client.post(
            "/api/coze/confirm_and_publish",
            json={
                "checkin_id": start_payload["checkin_id"],
                "content": publish_content,
            },
            headers={
                "X-Feishu-User-Id": "smoke-test-user",
                "X-Coze-Plugin-Token": settings.coze_plugin_token,
            },
        )
        if publish_response.status_code != 200:
            raise RuntimeError(
                f"Local confirm_and_publish failed: {publish_response.status_code} {publish_response.text}"
            )
        publish_payload = publish_response.json()

    return {
        "get_hot_topics_status": hot_topics_response.status_code,
        "topic_count": len(topics),
        "first_topic_keys": sorted(first.keys()),
        "has_hot_url_key": "hot_url" in first,
        "first_topic_has_hot_url_value": bool(first.get("hot_url")),
        "quick_generate_char_count": quick_payload.get("char_count", 0),
        "start_deep_mode_status": start_payload.get("status"),
        "deep_mode_message_status": message_payload.get("status"),
        "deep_mode_has_draft": message_payload.get("has_draft", False),
        "confirm_and_publish_points": publish_payload.get("points_earned", 0),
        "confirm_and_publish_streak": publish_payload.get("streak", 0),
    }


def main() -> None:
    validate_settings()
    live = asyncio.run(live_bitable_checks())
    plugin = local_plugin_check()
    print(json.dumps({"bitable": live, "plugin": plugin}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
