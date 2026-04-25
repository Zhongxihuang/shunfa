
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import User
from ..services.reminder_service import (
    check_reminder_needed,
    is_wechat_reminder_configured,
    send_due_reminders,
    update_reminder_settings,
)

router = APIRouter()

class ReminderSettingsRequest(BaseModel):
    reminder_time: str | None = None  # HH:MM or null to clear
    reminder_enabled: bool

class ReminderStatusResponse(BaseModel):
    reminder_enabled: bool
    reminder_time: str | None
    reminder_needed: bool  # True if user should be reminded right now
    wechat_push_configured: bool = False


class SendReminderResponse(BaseModel):
    checked: int
    sent: int
    skipped: int
    failed: int

@router.post("/reminder", response_model=ReminderStatusResponse)
async def set_reminder(
    request: ReminderSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Set reminder time and enable/disable reminder."""
    try:
        update_reminder_settings(
            current_user,
            request.reminder_time,
            request.reminder_enabled,
            db
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    reminder_needed = check_reminder_needed(current_user, db)

    return ReminderStatusResponse(
        reminder_enabled=current_user.reminder_enabled,
        reminder_time=current_user.reminder_time,
        reminder_needed=reminder_needed,
        wechat_push_configured=is_wechat_reminder_configured(),
    )

@router.get("/reminder_status", response_model=ReminderStatusResponse)
async def get_reminder_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get reminder settings and whether reminder is needed now."""
    reminder_needed = check_reminder_needed(current_user, db)

    return ReminderStatusResponse(
        reminder_enabled=current_user.reminder_enabled,
        reminder_time=current_user.reminder_time,
        reminder_needed=reminder_needed,
        wechat_push_configured=is_wechat_reminder_configured(),
    )


@router.post("/reminder/send_due", response_model=SendReminderResponse)
async def trigger_due_reminders(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if current_user.openid != "web_admin":
        raise HTTPException(status_code=403, detail="Only web admin can trigger reminder sends")

    result = await send_due_reminders(db)
    return SendReminderResponse(**result)
