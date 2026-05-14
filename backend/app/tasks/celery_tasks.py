"""
Celery tasks for 顺发 async background jobs.

Tasks are triggered by Celery Beat (celerybeat) on schedule, or can be
called manually via .delay() / .apply_async() from routers or cron scripts.

Note: These tasks run OUTSIDE the FastAPI request lifecycle, so they manage
their own database sessions rather than using FastAPI's Depends() injection.
"""

import logging

from celery import shared_task

from ..services.hot_topic_refresh_service import refresh_hot_topic_supply

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
            result = await refresh_hot_topic_supply()
            logger.info(f"[rss_task] Hot topic supply result: {result}")
            return result

        return asyncio.run(_run())

    except Exception as exc:
        logger.exception(f"[rss_task] Failed: {exc}")
        raise self.retry(exc=exc) from exc
