from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db, get_resolved_api_key
from ..models import HotTopic, User
from ..schemas import (
    HotTopicAnalysisRequest,
    HotTopicAnalysisResponse,
    HotTopicListItem,
    HotTopicsResponse,
)
from ..services.hot_topic_service import analyze_hot_topic
from ..services.local_hot_topic_store import get_topics_for_date, to_list_items
from ..utils.time_utils import get_today_cst

router = APIRouter()


async def refresh_hot_topics_directly() -> dict:
    from ..services.hot_topic_service import score_and_filter
    from ..services.local_hot_topic_store import replace_topics_for_date
    from ..services.rss_service import fetch_all_sources

    articles = await fetch_all_sources()
    if not articles:
        return {"status": "ok", "articles": 0, "topics": 0}

    topics = await score_and_filter(articles)
    if topics:
        replace_topics_for_date(topics, get_today_cst())

    return {"status": "ok", "articles": len(articles), "topics": len(topics)}


def get_today_hot_topic_or_404(topic_id: int, db: Session) -> HotTopic:
    topic = db.query(HotTopic).filter(
        HotTopic.id == topic_id,
        HotTopic.topic_date == get_today_cst(),
    ).first()
    if not topic:
        raise HTTPException(status_code=404, detail="今日热点不存在")
    return topic


@router.get("/hot_topics/today", response_model=HotTopicsResponse)
async def get_today_hot_topics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = get_today_cst()
    records = get_topics_for_date(topic_date=today, limit=3, db=db)
    return HotTopicsResponse(
        date=today,
        topics=to_list_items(records),
    )


@router.get("/hot_topics/{topic_id}", response_model=HotTopicListItem)
async def get_hot_topic_detail(
    topic_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    topic = get_today_hot_topic_or_404(topic_id, db)
    return to_list_items([topic])[0]


@router.post("/hot_topics/{topic_id}/analysis", response_model=HotTopicAnalysisResponse)
async def analyze_hot_topic_endpoint(
    topic_id: int,
    body: HotTopicAnalysisRequest | None = None,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    topic = get_today_hot_topic_or_404(topic_id, db)
    result = await analyze_hot_topic(
        title=topic.title,
        source=topic.source,
        published_at=topic.published_at,
        summary=topic.summary or "",
        ai_angle=topic.ai_angle or "",
        ai_counter_angle=topic.ai_counter_angle or "",
        angle=body.angle if body else None,
        api_key=api_key,
    )
    return HotTopicAnalysisResponse(**result)


@router.post("/hot_topics/refresh")
async def refresh_hot_topics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger a hot topics refresh. Runs synchronously and returns the result.
    Falls back to direct execution when Celery is not available.
    """
    try:
        from app.tasks.celery_tasks import fetch_hot_topics
        task = fetch_hot_topics.delay()
        return {
            "message": "热点刷新任务已提交",
            "task_id": task.id,
            "async": True,
        }
    except Exception:
        # Celery not available — run directly in this request.
        result = await refresh_hot_topics_directly()
        return {
            "message": "热点刷新已完成",
            "result": result,
            "async": False,
        }
