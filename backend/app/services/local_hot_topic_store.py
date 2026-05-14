from datetime import date

from cachetools import TTLCache
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..metrics import HOT_TOPIC_CACHE_HITS, HOT_TOPIC_CACHE_MISSES
from ..models import HotTopic
from ..schemas import HotTopicListItem, ScoredTopic
from ..utils.time_utils import get_today_cst

# In-memory TTL cache: keyed by date string, expires after 12 hours (43200 seconds).
# This eliminates a SQLite query on every /hot_topics/today call.
_hot_topic_cache: TTLCache = TTLCache(maxsize=8, ttl=43200)

FALLBACK_TOPICS = [
    {
        "title": "AI产品进入日常工作流",
        "summary": "当模型能力接近时，真正拉开差距的是谁能把AI嵌进稳定、可重复的工作流程。",
        "source": "顺发兜底",
        "url": "https://example.com/shunfa-hot-topic-fallback-ai-workflow",
        "category": "ai_product",
        "score": 7,
        "ai_angle": "AI竞争的重点正在从模型参数转向工作流落地",
        "ai_counter_angle": "没有真实场景验证的AI工作流很容易变成演示工程",
    },
    {
        "title": "内容创作者开始重视分发效率",
        "summary": "创作不只是写出观点，还要能快速生成标题、标签、图文素材并完成发布闭环。",
        "source": "顺发兜底",
        "url": "https://example.com/shunfa-hot-topic-fallback-content",
        "category": "industry",
        "score": 7,
        "ai_angle": "内容生产的瓶颈正在从写作转向稳定分发",
        "ai_counter_angle": "效率工具不能替代真正有判断力的内容观点",
    },
    {
        "title": "自动化工具需要更可靠的兜底机制",
        "summary": "用户不关心后台哪一步失败，只关心关键链路能不能持续给出可用结果。",
        "source": "顺发兜底",
        "url": "https://example.com/shunfa-hot-topic-fallback-reliability",
        "category": "tech",
        "score": 7,
        "ai_angle": "产品稳定性来自主链路收敛和失败兜底",
        "ai_counter_angle": "兜底内容只能保链路，不能替代高质量实时热点",
    },
]


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
    owns_session = db is None

    # Only use the process-local cache when this helper owns the DB session.
    # Request-scoped sessions should read fresh data because tests, admin jobs,
    # and migrations may write directly without going through replace_topics_for_date().
    if owns_session:
        cached = _hot_topic_cache.get(cache_key)
        if cached is not None:
            HOT_TOPIC_CACHE_HITS.inc()
            return cached[:limit]

        HOT_TOPIC_CACHE_MISSES.inc()

    # Cache miss — query DB
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
        if owns_session:
            # Store in cache (keep the full list so future limit values hit cache too)
            _hot_topic_cache[cache_key] = result
        return result
    finally:
        if owns_session:
            session.close()


def get_latest_topics(
    limit: int = 3,
    db: Session | None = None,
) -> tuple[date | None, list[HotTopic]]:
    """Return the newest stored hot topics, regardless of date."""
    owns_session = db is None
    session = db or SessionLocal()

    try:
        latest_date = (
            session.query(HotTopic.topic_date)
            .order_by(HotTopic.topic_date.desc())
            .limit(1)
            .scalar()
        )
        if latest_date is None:
            return None, []
        return latest_date, get_topics_for_date(topic_date=latest_date, limit=limit, db=session)
    finally:
        if owns_session:
            session.close()


def ensure_topics_for_date(
    topic_date: date | None = None,
    limit: int = 3,
    db: Session | None = None,
) -> list[HotTopic]:
    """Ensure the requested date has selectable local topics.

    If today's refresh did not produce topics, clone the latest successful batch
    into today so downstream detail/compose calls still use valid today topic IDs.
    If the database has never had topics, seed a small evergreen fallback batch.
    """
    effective_date = topic_date or get_today_cst()
    owns_session = db is None
    session = db or SessionLocal()

    try:
        existing = get_topics_for_date(topic_date=effective_date, limit=limit, db=session)
        if existing:
            return existing

        latest_date, latest_topics = get_latest_topics(limit=limit, db=session)
        source_topics = latest_topics if latest_date is not None else []

        seeded: list[HotTopic] = []
        if source_topics:
            for index, topic in enumerate(source_topics[:limit], start=1):
                seeded.append(
                    HotTopic(
                        topic_date=effective_date,
                        rank=index,
                        title=topic.title,
                        summary=topic.summary,
                        source=topic.source,
                        url=topic.url,
                        published_at=topic.published_at,
                        category=topic.category,
                        score=topic.score,
                        ai_angle=topic.ai_angle,
                        ai_counter_angle=topic.ai_counter_angle,
                    )
                )
        else:
            for index, topic in enumerate(FALLBACK_TOPICS[:limit], start=1):
                seeded.append(
                    HotTopic(
                        topic_date=effective_date,
                        rank=index,
                        title=topic["title"],
                        summary=topic["summary"],
                        source=topic["source"],
                        url=topic["url"],
                        category=topic["category"],
                        score=topic["score"],
                        ai_angle=topic["ai_angle"],
                        ai_counter_angle=topic["ai_counter_angle"],
                    )
                )

        try:
            for record in seeded:
                session.add(record)
            session.commit()
        except IntegrityError:
            session.rollback()
            return get_topics_for_date(topic_date=effective_date, limit=limit, db=session)

        for record in seeded:
            session.refresh(record)

        _hot_topic_cache.pop(str(effective_date), None)
        return seeded
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
