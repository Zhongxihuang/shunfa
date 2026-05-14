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
from ..services.hot_topic_refresh_service import refresh_hot_topic_supply
from ..services.hot_topic_service import analyze_hot_topic
from ..services.local_hot_topic_store import ensure_topics_for_date, to_list_items
from ..utils.time_utils import get_today_cst

router = APIRouter()


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
    records = ensure_topics_for_date(topic_date=today, limit=3, db=db)
    return HotTopicsResponse(
        date=today,
        topics=to_list_items(records),
    )


@router.get("/hot_topics/health")
async def get_hot_topics_health(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = get_today_cst()
    today_count = db.query(HotTopic).filter(HotTopic.topic_date == today).count()
    latest_date = (
        db.query(HotTopic.topic_date)
        .order_by(HotTopic.topic_date.desc())
        .limit(1)
        .scalar()
    )
    latest_count = 0
    if latest_date is not None:
        latest_count = db.query(HotTopic).filter(HotTopic.topic_date == latest_date).count()

    return {
        "status": "ok" if today_count > 0 else "degraded",
        "today": today.isoformat(),
        "today_count": today_count,
        "latest_date": latest_date.isoformat() if latest_date is not None else None,
        "latest_count": latest_count,
    }


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
    """Trigger a synchronous refresh and ensure Web has usable hot topics."""
    result = await refresh_hot_topic_supply(db=db)
    return {
        "message": "热点刷新已完成",
        "result": result,
        "async": False,
    }
