from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import TopicsResponse, TopicCard, SelectTopicRequest, SelectTopicResponse
from ..services.topic_service import generate_topics
from ..models import CheckIn, CheckInStatus
from ..utils.time_utils import get_today_cst
from ..services.content_service import reset_checkin_for_new_topic

router = APIRouter()

@router.post("/daily_topics", response_model=TopicsResponse)
async def get_daily_topics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get today's topic suggestions (max 3 refreshes per day)."""
    try:
        result = await generate_topics(current_user.id, db)
        return TopicsResponse(
            topics=[TopicCard(**t) for t in result["topics"]],
            refresh_count=result["refresh_count"],
            max_refreshes=3
        )
    except ValueError as e:
        raise HTTPException(status_code=429, detail=str(e))

@router.post("/select_topic", response_model=SelectTopicResponse)
async def select_topic(
    request: SelectTopicRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Select a topic (either from suggestions or custom input)."""
    today = get_today_cst()

    # Check if already has today's completed check-in
    existing = db.query(CheckIn).filter(
        CheckIn.user_id == current_user.id,
        CheckIn.date == today,
        CheckIn.status == CheckInStatus.completed
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="今日已完成打卡")

    # Get or create today's check-in
    checkin = db.query(CheckIn).filter(
        CheckIn.user_id == current_user.id,
        CheckIn.date == today
    ).first()

    if checkin:
        reset_checkin_for_new_topic(checkin, request.topic, CheckInStatus.topic_selected)
    else:
        checkin = CheckIn(
            user_id=current_user.id,
            date=today,
            topic=request.topic,
            status=CheckInStatus.topic_selected,
            refresh_count=0
        )
        db.add(checkin)

    # Mark topic as used in history
    from ..models import TopicHistory
    if request.batch_id:
        # Suggested topic: use batch_id for precise lookup
        topic_history = db.query(TopicHistory).filter(
            TopicHistory.user_id == current_user.id,
            TopicHistory.topic == request.topic,
            TopicHistory.batch_id == request.batch_id
        ).first()
    else:
        # Custom topic: find most recent matching entry
        topic_history = db.query(TopicHistory).filter(
            TopicHistory.user_id == current_user.id,
            TopicHistory.topic == request.topic
        ).order_by(TopicHistory.created_at.desc()).first()
    if topic_history:
        topic_history.was_used = True

    db.commit()
    db.refresh(checkin)

    return SelectTopicResponse(checkin_id=checkin.id, status=checkin.status)
