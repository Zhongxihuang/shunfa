"""
Celery tasks for 顺发 async background jobs.

Tasks are triggered by Celery Beat (celerybeat) on schedule, or can be
called manually via .delay() / .apply_async() from routers or cron scripts.

Note: These tasks run OUTSIDE the FastAPI request lifecycle, so they manage
their own database sessions rather than using FastAPI's Depends() injection.
"""

import logging

from celery import shared_task

from ..services.hot_topic_service import score_and_filter
from ..services.local_hot_topic_store import replace_topics_for_date
from ..services.rss_service import fetch_all_sources
from ..utils.time_utils import get_today_cst

logger = logging.getLogger("celery_tasks")


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def fetch_hot_topics(self) -> dict:
    """
    Fetch RSS sources, score articles via AI, and store to hot topics DB.
    Runs twice daily (noon + evening CST) via Celery Beat.

    Retries: up to 3 times with 60s backoff on transient failures.
    """
    logger.info("[rss_task] Starting RSS hot topic fetch")
    try:
        import asyncio

        async def _run():
            articles = await fetch_all_sources()
            logger.info(f"[rss_task] Fetched {len(articles)} articles")

            if not articles:
                logger.warning("[rss_task] No articles fetched")
                return {"status": "ok", "articles": 0, "topics": 0}

            topics = await score_and_filter(articles)
            logger.info(f"[rss_task] {len(topics)} topics qualified")

            if topics:
                today = get_today_cst()
                replace_topics_for_date(topics, today)
                logger.info(f"[rss_task] Stored {len(topics)} topics for {today}")

            return {"status": "ok", "articles": len(articles), "topics": len(topics)}

        return asyncio.run(_run())

    except Exception as exc:
        logger.exception(f"[rss_task] Failed: {exc}")
        raise self.retry(exc=exc) from exc
