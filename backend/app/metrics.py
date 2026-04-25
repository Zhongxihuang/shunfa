"""
Custom Prometheus metrics for 顺发.

Metrics are defined as module-level Counter/Histogram/Gauge variables
so they can be imported anywhere in the codebase without circular-import issues.

Usage in a service:
    from app.metrics import (
        CHECKINS_TOTAL,
        AI_LATENCY_SECONDS,
        PUBLISH_TOTAL,
        SLOW_REQUEST_COUNT,
    )

    CHECKINS_TOTAL.labels(status="completed").inc()
    AI_LATENCY_SECONDS.labels(operation="chat_completion").observe(1.23)
"""

from prometheus_client import Counter, Gauge, Histogram

# ── Check-in counters ───────────────────────────────────────────────────────
CHECKINS_TOTAL = Counter(
    "shunfa_checkins_total",
    "Total number of check-ins by final status",
    ["status"],  # topic_selected, discussing, draft_ready, pending, completed
)

# ── AI operation latency ─────────────────────────────────────────────────────
AI_LATENCY_SECONDS = Histogram(
    "shunfa_ai_latency_seconds",
    "Latency of AI (DeepSeek) API calls in seconds",
    ["operation"],  # chat_completion, quick_generate, quality_check
    buckets=(0.5, 1.0, 2.0, 4.0, 8.0, 16.0, 32.0, 64.0),
)

# ── Publish counter ──────────────────────────────────────────────────────────
PUBLISH_TOTAL = Counter(
    "shunfa_publish_total",
    "Total number of successful publishes",
)

# ── Streak / points gauge ───────────────────────────────────────────────────
CURRENT_STREAK_GAUGE = Gauge(
    "shunfa_current_streak_max",
    "Highest current streak across all users (sample)",
)

# ── Hot topic cache hit rate ────────────────────────────────────────────────
HOT_TOPIC_CACHE_HITS = Counter(
    "shunfa_hot_topic_cache_hits_total",
    "Hot topic cache hits (TTL cache)",
)

HOT_TOPIC_CACHE_MISSES = Counter(
    "shunfa_hot_topic_cache_misses_total",
    "Hot topic cache misses (fell through to DB)",
)

# ── Reminder delivery counter ────────────────────────────────────────────────
REMINDER_SENT_TOTAL = Counter(
    "shunfa_reminder_sent_total",
    "Total WeChat reminders sent",
    ["status"],  # sent, skipped, failed
)

# ── Slow request tracking ───────────────────────────────────────────────────
SLOW_REQUEST_COUNT = Counter(
    "shunfa_slow_requests_total",
    "Requests that exceeded the slow-request threshold",
    ["method", "path", "status_code"],
)

# ── Celery task metrics ─────────────────────────────────────────────────────
CELERY_TASK_RUNS = Counter(
    "shunfa_celery_task_runs_total",
    "Celery task executions",
    ["task_name", "result"],  # result: success, failure, retry
)

CELERY_TASK_LATENCY = Histogram(
    "shunfa_celery_task_latency_seconds",
    "Celery task execution time in seconds",
    ["task_name"],
    buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
)
