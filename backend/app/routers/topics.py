from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db, get_resolved_api_key
from ..models import CheckIn, CheckInStatus, HotTopic, User
from ..rate_limit import limiter
from ..schemas import SelectTopicRequest, SelectTopicResponse, TopicCard, TopicsResponse
from ..services.analytics import track
from ..services.discussion_service import reset_checkin_for_new_topic
from ..services.generation_context import update_generation_context
from ..services.topic_service import generate_topics
from ..utils.time_utils import get_today_cst

router = APIRouter()


def get_today_hot_topic_or_404(hot_topic_id: int, db: Session) -> HotTopic:
    topic = (
        db.query(HotTopic)
        .filter(
            HotTopic.id == hot_topic_id,
            HotTopic.topic_date == get_today_cst(),
        )
        .first()
    )
    if not topic:
        raise HTTPException(status_code=404, detail="今日热点不存在")
    return topic


@router.post("/daily_topics", response_model=TopicsResponse)
@limiter.limit("10/minute")
async def get_daily_topics(
    request: Request,
    current_user: User = Depends(get_current_user),
    api_key: str = Depends(get_resolved_api_key),
    db: Session = Depends(get_db),
):
    """Get today's topic suggestions (max 3 refreshes per day)."""
    try:
        result = await generate_topics(current_user.id, db, api_key)
        return TopicsResponse(
            topics=[TopicCard(**t) for t in result["topics"]],
            refresh_count=result["refresh_count"],
            max_refreshes=3,
        )
    except ValueError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc


@router.post("/select_topic", response_model=SelectTopicResponse)
async def select_topic(
    request: SelectTopicRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Select a topic (either from suggestions or custom input)."""
    today = get_today_cst()

    existing = (
        db.query(CheckIn)
        .filter(
            CheckIn.user_id == current_user.id,
            CheckIn.date == today,
            CheckIn.status == CheckInStatus.completed,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="今日已完成打卡")

    checkin = (
        db.query(CheckIn).filter(CheckIn.user_id == current_user.id, CheckIn.date == today).first()
    )

    selected_topic = None
    if request.hot_topic_id is not None:
        selected_topic = get_today_hot_topic_or_404(request.hot_topic_id, db)

    topic_text = selected_topic.title if selected_topic else request.topic

    if checkin:
        reset_checkin_for_new_topic(checkin, topic_text, CheckInStatus.topic_selected)
    else:
        checkin = CheckIn(
            user_id=current_user.id,
            date=today,
            topic=topic_text,
            status=CheckInStatus.topic_selected,
            refresh_count=0,
        )
        db.add(checkin)

    if selected_topic:
        checkin.topic = selected_topic.title
        checkin.topic_source = selected_topic.source
        checkin.topic_url = selected_topic.url
        checkin.topic_summary = selected_topic.summary
        checkin.topic_published_at = selected_topic.published_at
        update_generation_context(
            checkin,
            hot_topic_id=selected_topic.id,
            hot_topic_score=selected_topic.score,
            hot_topic_category=selected_topic.category,
            source_angle=selected_topic.ai_angle,
            counter_angle=selected_topic.ai_counter_angle,
            selected_angle=request.selected_angle,
            platform=request.platform.value if request.platform else None,
        )
    elif request.selected_angle or request.platform:
        update_generation_context(
            checkin,
            selected_angle=request.selected_angle,
            platform=request.platform.value if request.platform else None,
        )

    from ..models import TopicHistory

    if request.batch_id:
        topic_history = (
            db.query(TopicHistory)
            .filter(
                TopicHistory.user_id == current_user.id,
                TopicHistory.topic == topic_text,
                TopicHistory.batch_id == request.batch_id,
            )
            .first()
        )
    else:
        topic_history = (
            db.query(TopicHistory)
            .filter(TopicHistory.user_id == current_user.id, TopicHistory.topic == topic_text)
            .order_by(TopicHistory.created_at.desc())
            .first()
        )
    if topic_history:
        topic_history.was_used = True

    db.commit()
    db.refresh(checkin)

    track(
        "topic_selected",
        user_id=current_user.id,
        props={
            "checkin_id": checkin.id,
            "source": "hot_topic" if selected_topic else "custom",
            "platform": request.platform.value if request.platform else None,
        },
    )
    return SelectTopicResponse(checkin_id=checkin.id, status=checkin.status)
