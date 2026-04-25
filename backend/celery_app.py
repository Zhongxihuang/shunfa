"""
Celery application for 顺发 async task queue.

Broker: Redis (configured via REDIS_URL env var, default: redis://localhost:6379/0)
Backend: Redis

Run worker:
    celery -A celery_app worker --loglevel=info

Run beat (scheduler):
    celery -A celery_app beat --loglevel=info

Or both together (for development):
    celery -A celery_app worker --loglevel=info --scheduler celery.beat:PersistentScheduler
"""

import os
from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "shunfa",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks.celery_tasks"],
)

# ── Celery configuration ────────────────────────────────────────────────────
celery_app.conf.update(
    # Serialization
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    # Retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    # Visibility timeout (time before unacknowledged tasks are redelivered)
    visibility_timeout=3600,
    # Task result expiry
    result_expires=86400,
    # Beat schedule (replaces system cron for reminder + RSS tasks)
    beat_schedule={
        # RSS hot topics: twice daily at 12:00 and 19:00 CST
        "rss-fetch-noon": {
            "task": "app.tasks.celery_tasks.fetch_hot_topics",
            "schedule": crontab(hour=12, minute=0, timezone="Asia/Shanghai"),
        },
        "rss-fetch-evening": {
            "task": "app.tasks.celery_tasks.fetch_hot_topics",
            "schedule": crontab(hour=19, minute=0, timezone="Asia/Shanghai"),
        },
        # WeChat reminders: every 30 minutes during active hours
        "wechat-reminder": {
            "task": "app.tasks.celery_tasks.send_due_reminders",
            "schedule": crontab(hour="*/2", minute=30, timezone="Asia/Shanghai"),
            # Only send if within active window (9:00–22:00 CST) — checked inside the task
        },
    },
)
