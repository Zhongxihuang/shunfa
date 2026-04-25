from datetime import date

from cachetools import TTLCache
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..metrics import HOT_TOPIC_CACHE_HITS, HOT_TOPIC_CACHE_MISSES
from ..models import HotTopic
from ..schemas import HotTopicListItem, ScoredTopic
from ..utils.time_utils import get_today_cst

# In-memory TTL cache: keyed by date string, expires after 12 hours (43200 seconds).
# This eliminates a SQLite query on every /hot_topics/today call.
_hot_topic_cache: TTLCache = TTLCache(maxsize=8, ttl=43200)


def replace_topics_for_date(
    topics: list[ScoredTopic],
    topic_date: date | None = None,
    db: Session | None = None,
) -> list[HotTopic]:
    effective_date = topic_date or get_today_cst()
    owns_session = db is None
    session = db or SessionLocal()

    try:
        session.query(HotTopic).filter(HotTopic.topic_date == effective_date).delete()

        saved: list[HotTopic] = []
        for index, topic in enumerate(topics, start=1):
            record = HotTopic(
                topic_date=effective_date,
                rank=index,
                title=topic.hot_topic,
                summary=topic.hot_summary,
                source=topic.hot_source,
                url=topic.hot_url,
                published_at=topic.published_at,
                category=topic.topic_category.value,
                score=topic.score,
                ai_angle=topic.ai_angle,
                ai_counter_angle=topic.ai_counter_angle,
            )
            session.add(record)
            saved.append(record)

        session.commit()
        for record in saved:
            session.refresh(record)

        # Invalidate cache so next read gets fresh data
        _hot_topic_cache.pop(str(effective_date), None)
        return saved
    finally:
        if owns_session:
            session.close()


def get_topics_for_date(
    topic_date: date | None = None,
    limit: int = 3,
    db: Session | None = None,
) -> list[HotTopic]:
    effective_date = topic_date or get_today_cst()
    cache_key = str(effective_date)

    # Try cache first
    cached = _hot_topic_cache.get(cache_key)
    if cached is not None:
        HOT_TOPIC_CACHE_HITS.inc()
        return cached[:limit]

    HOT_TOPIC_CACHE_MISSES.inc()

    # Cache miss — query DB
    owns_session = db is None
    session = db or SessionLocal()

    try:
        records = session.query(HotTopic).filter(
            HotTopic.topic_date == effective_date
        ).all()

        boost_map = {
            "雷锋网": 5,
            "36Kr": 5,
            "Hacker News": -5,
        }
        records.sort(key=lambda r: (r.score + boost_map.get(r.source, 0), r.title), reverse=True)

        result = records[:limit]
        # Store in cache (keep the full list so future limit values hit cache too)
        _hot_topic_cache[cache_key] = result
        return result
    finally:
        if owns_session:
            session.close()


def to_list_items(records: list[HotTopic]) -> list[HotTopicListItem]:
    return [
        HotTopicListItem(
            id=record.id,
            title=record.title,
            summary=record.summary or "",
            source=record.source,
            url=record.url,
            published_at=record.published_at,
            score=record.score,
            category=record.category,
            ai_angle=record.ai_angle or "",
            ai_counter_angle=record.ai_counter_angle or "",
        )
        for record in records
    ]
