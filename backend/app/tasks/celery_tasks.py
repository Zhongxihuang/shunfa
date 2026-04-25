"""
Celery tasks for 顺发 async background jobs.

Tasks are triggered by Celery Beat (celerybeat) on schedule, or can be
called manually via .delay() / .apply_async() from routers or cron scripts.

Note: These tasks run OUTSIDE the FastAPI request lifecycle, so they manage
their own database sessions rather than using FastAPI's Depends() injection.
"""

import logging

from celery import shared_task

from ..database import SessionLocal
from ..services.hot_topic_service import score_and_filter
from ..services.local_hot_topic_store import replace_topics_for_date
from ..services.reminder_service import send_due_reminders
from ..services.rss_service import fetch_all_sources
from ..utils.time_utils import get_now_cst, get_today_cst

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
        # Synchronous wrapper — run async code in sync context
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


@shared_task(bind=True, max_retries=3, default_retry_delay=120)
def send_due_reminders_task(self) -> dict:
    """
    Check and send WeChat subscription reminders to all enabled users.
    Runs every 2 hours (9:30, 11:30, ..., 21:30) CST via Celery Beat.

    Only sends if current time is within the active reminder window
    (reminder_time to reminder_time + 2h), preventing off-hours spam.

    Retries: up to 3 times with 2min backoff on failures.
    """
    now = get_now_cst()
    active_hour = now.hour

    # Skip if outside active hours (off-peak times when reminders don't fire)
    if active_hour < 9 or active_hour > 21:
        logger.debug(f"[reminder_task] Skipped — outside active hours ({active_hour}:{now.minute})")
        return {"status": "skipped", "reason": "outside_active_hours", "checked": 0}

    logger.info(f"[reminder_task] Starting reminder check at {now}")
    db = SessionLocal()
    try:
        import asyncio

        async def _run():
            return await send_due_reminders(db)

        result = asyncio.run(_run())
        logger.info(
            f"[reminder_task] Done: checked={result['checked']} "
            f"sent={result['sent']} skipped={result['skipped']} failed={result['failed']}"
        )
        return result
    except Exception as exc:
        logger.exception(f"[reminder_task] Failed: {exc}")
        raise self.retry(exc=exc) from exc
    finally:
        db.close()


# ── One-shot task (for manual trigger from router) ──────────────────────────

@shared_task(bind=True)
def send_single_reminder(self, user_id: int) -> dict:
    """
    Send a single WeChat reminder to a specific user (by ID).
    Can be called from reminder router when user updates their reminder settings.
    """
    from ..models import User

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return {"sent": False, "status": "error", "reason": "user_not_found"}

        import asyncio

        async def _run():
            return await send_due_reminders(db)

        return asyncio.run(_run())
    finally:
        db.close()
