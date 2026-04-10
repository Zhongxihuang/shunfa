"""Refresh today's hot topics in Bitable.

This script expires today's pending hot topics, fetches fresh RSS articles,
re-scores them, and writes a fresh batch for today.

Usage:
    cd backend && python -m scripts.refresh_today_hot_topics
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from app.clients.bitable_client import get_bitable_client
from app.config import settings
from app.services.hot_topic_service import score_and_filter
from app.services.hot_topic_store import get_pending_topics, save_topics
from app.services.rss_service import fetch_all_sources


async def expire_today_pending() -> dict:
    client = get_bitable_client()
    table_id = settings.bitable_hot_topic_table_id
    today = date.today()
    data = await client.list_records(
        table_id,
        filter_formula=(
            f'AND(CurrentValue.[status] = "pending",'
            f'CurrentValue.[date] = "{today.isoformat()}")'
        ),
        page_size=100,
    )
    items = data.get("items", [])
    if not items:
        return {"expired_count": 0, "record_ids": []}

    updates = [
        {"record_id": item["record_id"], "fields": {"status": "expired"}}
        for item in items
    ]
    await client.batch_update_records(table_id, updates)
    return {"expired_count": len(items), "record_ids": [item["record_id"] for item in items]}


async def main() -> None:
    expired = await expire_today_pending()
    articles = await fetch_all_sources()
    topics = await score_and_filter(articles)
    created_ids = await save_topics(topics, topic_date=date.today())
    refreshed = await get_pending_topics(limit=10)

    print(
        json.dumps(
            {
                "expired": expired,
                "fetched_articles": len(articles),
                "qualified_topics": len(topics),
                "created_count": len(created_ids),
                "non_empty_hot_url_count": sum(1 for t in refreshed if t.hot_url),
                "sample_topics": [
                    {
                        "hot_topic": t.hot_topic,
                        "hot_url": t.hot_url,
                        "score": t.score,
                    }
                    for t in refreshed[:5]
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
