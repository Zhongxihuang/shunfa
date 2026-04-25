
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import CheckIn, CheckInStatus, User
from ..schemas import CheckInHistoryItem, CheckInHistoryResponse

router = APIRouter()


@router.get("/my/checkins", response_model=CheckInHistoryResponse)
async def get_my_checkins(
    status_filter: str | None = Query(None, description="Filter by status: completed, draft, discussing"),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的所有 checkin 记录（创作历史）。"""
    query = db.query(CheckIn).filter(CheckIn.user_id == current_user.id)

    if status_filter == "completed":
        query = query.filter(CheckIn.status == CheckInStatus.completed)
    elif status_filter == "draft":
        query = query.filter(CheckIn.status != CheckInStatus.completed)
    elif status_filter == "discussing":
        query = query.filter(CheckIn.status.in_([CheckInStatus.discussing, CheckInStatus.topic_selected]))

    total = query.count()

    checkins = (
        query.order_by(CheckIn.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    # draft count
    draft_count = (
        db.query(CheckIn)
        .filter(
            CheckIn.user_id == current_user.id,
            CheckIn.status != CheckInStatus.completed,
        )
        .count()
    )

    items = [
        CheckInHistoryItem(
            id=c.id,
            date=c.date,
            topic=c.topic,
            topic_source=c.topic_source,
            content=c.content,
            status=c.status.value,
            points_earned=c.points_earned,
            created_at=c.created_at,
        )
        for c in checkins
    ]

    return CheckInHistoryResponse(
        checkins=items,
        total=total,
        draft_count=draft_count,
    )
