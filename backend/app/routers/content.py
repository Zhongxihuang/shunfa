from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, get_current_user
from ..models import User, CheckIn, CheckInStatus
from ..schemas import (
    MessageRequest, MessageResponse,
    ConfirmContentRequest, ConfirmPublishRequest, PublishResponse,
    SelectTopicRequest, SelectTopicResponse
)
from ..services.content_service import process_message, confirm_content, confirm_publish

router = APIRouter()

def get_checkin_or_404(checkin_id: int, user_id: int, db: Session) -> CheckIn:
    checkin = db.query(CheckIn).filter(
        CheckIn.id == checkin_id,
        CheckIn.user_id == user_id
    ).first()
    if not checkin:
        raise HTTPException(status_code=404, detail="CheckIn not found")
    return checkin

@router.post("/generate_content", response_model=MessageResponse)
async def generate_content(
    request: MessageRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message in the discussion flow."""
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)

    if checkin.status == CheckInStatus.completed:
        raise HTTPException(status_code=400, detail="今日已完成发布")

    if checkin.status not in (CheckInStatus.topic_selected, CheckInStatus.discussing):
        raise HTTPException(status_code=400, detail=f"当前状态不支持发送消息: {checkin.status.value}")

    # Change status to discussing if just started
    if checkin.status == CheckInStatus.topic_selected:
        checkin.status = CheckInStatus.discussing
        db.commit()

    result = await process_message(checkin, request.message, db)
    return MessageResponse(**result)

@router.post("/confirm_content")
async def confirm_content_endpoint(
    request: ConfirmContentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User confirms (possibly edited) draft content."""
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)

    try:
        await confirm_content(checkin, request.content, db)
        return {"status": "pending", "message": "内容已确认，可以发布了"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/confirm_publish", response_model=PublishResponse)
async def confirm_publish_endpoint(
    request: ConfirmPublishRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User confirms publish. Final step."""
    checkin = get_checkin_or_404(request.checkin_id, current_user.id, db)

    try:
        result = await confirm_publish(checkin, db, current_user)
        return PublishResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
