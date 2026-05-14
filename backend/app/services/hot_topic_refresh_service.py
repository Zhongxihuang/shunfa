"""Reliable hot topic refresh orchestration for the Web supply path."""

import logging

from sqlalchemy.orm import Session

from ..services.hot_topic_service import score_and_filter
from ..services.local_hot_topic_store import ensure_topics_for_date, replace_topics_for_date
from ..services.rss_service import fetch_all_sources
from ..utils.time_utils import get_today_cst

logger = logging.getLogger("hot_topic_refresh")


async def refresh_hot_topic_supply(db: Session | None = None) -> dict:
    """Refresh today's hot topics and always leave Web with selectable topics.

    Fresh RSS + AI topics are preferred. If fetching/scoring fails or produces no
    qualified topics, this seeds today's table from the latest local batch or the
    static fallback topics.
    """
    today = get_today_cst()
    articles_count = 0
    qualified_count = 0

    try:
        articles = await fetch_all_sources()
        articles_count = len(articles)
        if articles:
            topics = await score_and_filter(articles)
            qualified_count = len(topics)
            if topics:
                saved = replace_topics_for_date(topics, topic_date=today, db=db)
                return {
                    "status": "fresh",
                    "date": today.isoformat(),
                    "articles": articles_count,
                    "topics": qualified_count,
                    "available_topics": len(saved),
                    "fallback": False,
                }
    except Exception as exc:
        logger.exception("Hot topic refresh failed; falling back to local supply")
        available = ensure_topics_for_date(topic_date=today, limit=3, db=db)
        return {
            "status": "fallback_after_error",
            "date": today.isoformat(),
            "articles": articles_count,
            "topics": qualified_count,
            "available_topics": len(available),
            "fallback": True,
            "error": str(exc),
        }

    available = ensure_topics_for_date(topic_date=today, limit=3, db=db)
    return {
        "status": "fallback_no_fresh_topics",
        "date": today.isoformat(),
        "articles": articles_count,
        "topics": qualified_count,
        "available_topics": len(available),
        "fallback": True,
    }
