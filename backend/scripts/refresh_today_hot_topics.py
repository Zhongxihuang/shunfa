"""Refresh today's hot topics in the local hot_topics table.

This script fetches fresh RSS articles, scores them, and writes a fresh batch
for today. If no topic qualifies, it leaves existing local data intact.

Usage:
    cd backend && python -m scripts.refresh_today_hot_topics
"""

from __future__ import annotations

import asyncio
import json

from app.services.hot_topic_refresh_service import refresh_hot_topic_supply


async def main() -> None:
    result = await refresh_hot_topic_supply()
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
