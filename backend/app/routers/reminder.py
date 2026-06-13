from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..dependencies import get_current_user, get_db
from ..models import User
from ..services.reminder_service import check_reminder_needed, update_reminder_settings

router = APIRouter()


class ReminderSettingsRequest(BaseModel):
    reminder_time: str | None = None  # HH:MM or null to clear
    reminder_enabled: bool


class ReminderStatusResponse(BaseModel):
    reminder_enabled: bool
    reminder_time: str | None
    reminder_needed: bool


@router.post("/reminder", response_model=ReminderStatusResponse)
async def set_reminder(
    request: ReminderSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Set reminder time and enable/disable reminder."""
    try:
        update_reminder_settings(current_user, request.reminder_time, request.reminder_enabled, db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return ReminderStatusResponse(
        reminder_enabled=current_user.reminder_enabled,
        reminder_time=current_user.reminder_time,
        reminder_needed=check_reminder_needed(current_user, db),
    )


@router.get("/reminder_status", response_model=ReminderStatusResponse)
async def get_reminder_status(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get reminder settings and whether reminder is needed now."""
    return ReminderStatusResponse(
        reminder_enabled=current_user.reminder_enabled,
        reminder_time=current_user.reminder_time,
        reminder_needed=check_reminder_needed(current_user, db),
    )
