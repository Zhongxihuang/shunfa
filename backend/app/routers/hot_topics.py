from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import User
from ..schemas import HotTopicsResponse
from ..services.local_hot_topic_store import get_topics_for_date, to_list_items
from ..utils.time_utils import get_today_cst

router = APIRouter()


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


@router.post("/hot_topics/refresh", status_code=status.HTTP_202_ACCEPTED)
async def refresh_hot_topics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Trigger an async hot topics refresh via Celery task.
    Returns immediately — the actual refresh runs in the background.
    """
    from app.tasks.celery_tasks import fetch_hot_topics

    task = fetch_hot_topics.delay()
    return {
        "message": "热点刷新任务已提交",
        "task_id": task.id,
    }
