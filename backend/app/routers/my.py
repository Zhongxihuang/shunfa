from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import CheckIn, CheckInStatus, User
from ..schemas import (
    CheckInHistoryItem,
    CheckInHistoryResponse,
    DailyStatsItem,
    StatsResponse,
    StatsSummary,
)
from ..utils.time_utils import get_today_cst

router = APIRouter()


@router.get("/my/checkins", response_model=CheckInHistoryResponse)
async def get_my_checkins(
    status_filter: str | None = Query(
        None, description="Filter by status: completed, draft, discussing"
    ),
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
        query = query.filter(
            CheckIn.status.in_([CheckInStatus.discussing, CheckInStatus.topic_selected])
        )

    total = query.count()

    checkins = query.order_by(CheckIn.created_at.desc()).offset(offset).limit(limit).all()

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


@router.get("/my/stats", response_model=StatsResponse)
async def get_my_stats(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户近 30 天的内容质量统计（通过率趋势）。"""
    today = get_today_cst()
    thirty_days_ago = today - timedelta(days=30)

    # Query completed checkins in last 30 days
    checkins = (
        db.query(CheckIn)
        .filter(
            CheckIn.user_id == current_user.id,
            CheckIn.date >= thirty_days_ago,
            CheckIn.date <= today,
        )
        .order_by(CheckIn.date)
        .all()
    )

    # Aggregate by date
    daily_totals: dict[date, int] = {}
    daily_approved: dict[date, int] = {}
    for c in checkins:
        d = c.date
        daily_totals[d] = daily_totals.get(d, 0) + 1
        if c.content_approved:
            daily_approved[d] = daily_approved.get(d, 0) + 1

    # Fill in all 30 days, even with 0 values
    last_30_days = []
    for i in range(30):
        d = thirty_days_ago + timedelta(days=i)
        total = daily_totals.get(d, 0)
        approved = daily_approved.get(d, 0)
        approval_rate = (approved / total) if total > 0 else 0.0
        last_30_days.append(
            DailyStatsItem(
                date=d,
                total=total,
                approved=approved,
                approval_rate=round(float(approval_rate), 2),
            )
        )

    # Summary
    total_all = sum(daily_totals.values())
    approved_all = sum(daily_approved.values())
    summary = StatsSummary(
        total=total_all,
        approved=approved_all,
        approval_rate=round(float(approved_all / total_all), 2) if total_all > 0 else 0.0,
    )

    return StatsResponse(last_30_days=last_30_days, summary=summary)
