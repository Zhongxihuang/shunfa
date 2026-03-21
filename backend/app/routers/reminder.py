from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from ..dependencies import get_db, get_current_user
from ..models import User
from ..services.reminder_service import check_reminder_needed, update_reminder_settings

router = APIRouter()

class ReminderSettingsRequest(BaseModel):
    reminder_time: Optional[str] = None  # HH:MM or null to clear
    reminder_enabled: bool

class ReminderStatusResponse(BaseModel):
    reminder_enabled: bool
    reminder_time: Optional[str]
    reminder_needed: bool  # True if user should be reminded right now

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
        reminder_needed=reminder_needed
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
        reminder_needed=reminder_needed
    )
