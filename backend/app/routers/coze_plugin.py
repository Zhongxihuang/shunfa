"""Coze plugin API router.

These endpoints are called by Coze workflows as plugin actions.
All requests carry the Feishu user_id in the X-Feishu-User-Id header,
which maps to or creates a SQLite User record for streak/points tracking.

Endpoint prefix: /api/coze/
Auth: X-Coze-Plugin-Token header (shared secret) + X-Feishu-User-Id header
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from datetime import date

from ..dependencies import get_db
from ..models import User, CheckIn, CheckInStatus
from ..config import settings
from ..utils.time_utils import get_today_cst
from ..services.content_service import quick_generate, process_message, confirm_content, confirm_publish
from ..services.hot_topic_store import get_pending_topics, mark_as_pushed
from ..schemas import HotTopicRecord, Platform

router = APIRouter(prefix="/coze")


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_coze_user(
    x_feishu_user_id: str = Header(..., alias="X-Feishu-User-Id"),
    x_coze_plugin_token: str = Header(..., alias="X-Coze-Plugin-Token"),
    db: Session = Depends(get_db),
) -> User:
    """Extract Feishu user ID from Coze request headers and look up/create User."""
    if x_coze_plugin_token != settings.coze_plugin_token:
        raise HTTPException(status_code=401, detail="Invalid plugin token")

    # Use feishu_user_id as the openid for Coze users (prefixed to avoid collision)
    openid = f"feishu:{x_feishu_user_id}"
    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        user = User(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ── Request / Response models ─────────────────────────────────────────────────

class GetHotTopicsResponse(BaseModel):
    topics: List[dict]
    date: str


class QuickGeneratePluginRequest(BaseModel):
    hot_topic: str
    angle: str
    platform: str = "xiaohongshu"


class QuickGeneratePluginResponse(BaseModel):
    content: str
    platform: str
    char_count: int


class StartDeepModeRequest(BaseModel):
    hot_topic: str
    angle: str


class StartDeepModeResponse(BaseModel):
    checkin_id: int
    status: str
    opening_message: str


class DeepModeMessageRequest(BaseModel):
    checkin_id: int
    message: str
    angle: str = ""


class DeepModeMessageResponse(BaseModel):
    reply: str
    status: str
    draft: str = ""
    has_draft: bool = False


class ConfirmPublishRequest(BaseModel):
    checkin_id: int
    content: str


class ConfirmPublishResponse(BaseModel):
    streak: int
    points_earned: int
    total_points: int
    level: int
    message: str
    newly_unlocked: List[dict] = []


class UserStatsResponse(BaseModel):
    streak: int
    longest_streak: int
    points: int
    level: int
    diamonds: int
    today_completed: bool
    achievements: List[dict] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/get_hot_topics", response_model=GetHotTopicsResponse)
async def get_hot_topics(
    limit: int = 3,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Return today's top-scored pending hot topics for the daily push."""
    try:
        topics = await get_pending_topics(limit=limit)
    except Exception:
        # Bitable unavailable — return empty
        topics = []

    topic_list = [
        {
            "index": i + 1,
            "hot_topic": t.hot_topic,
            "hot_source": t.hot_source,
            "ai_angle": t.ai_angle,
            "ai_counter_angle": t.ai_counter_angle,
            "score": t.score,
            "category": t.topic_category.value,
            "record_id": t.record_id,
        }
        for i, t in enumerate(topics)
    ]

    return GetHotTopicsResponse(
        topics=topic_list,
        date=get_today_cst().isoformat(),
    )


@router.post("/quick_generate", response_model=QuickGeneratePluginResponse)
async def coze_quick_generate(
    request: QuickGeneratePluginRequest,
    current_user: User = Depends(get_coze_user),
):
    """Quick mode: generate content from hot topic + angle in ~30s. Stateless."""
    result = await quick_generate(
        hot_topic=request.hot_topic,
        angle=request.angle,
        platform=request.platform,
    )
    return QuickGeneratePluginResponse(**result)


@router.post("/start_deep_mode", response_model=StartDeepModeResponse)
async def start_deep_mode(
    request: StartDeepModeRequest,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Create a deep mode CheckIn session. Returns checkin_id for subsequent messages."""
    today = get_today_cst()

    # Reuse existing incomplete checkin for today, or create new one
    existing = db.query(CheckIn).filter(
        CheckIn.user_id == current_user.id,
        CheckIn.date == today,
        CheckIn.status != CheckInStatus.completed,
    ).first()

    if existing:
        checkin = existing
        checkin.topic = request.hot_topic
        db.commit()
    else:
        checkin = CheckIn(
            user_id=current_user.id,
            date=today,
            topic=request.hot_topic,
            status=CheckInStatus.discussing,
        )
        db.add(checkin)
        db.commit()
        db.refresh(checkin)

    # Generate opening angle suggestions
    from ..services.content_service import AUTO_SUGGEST_SENTINEL
    result = await process_message(
        checkin=checkin,
        user_message=AUTO_SUGGEST_SENTINEL,
        db=db,
        angle=request.angle,
    )

    return StartDeepModeResponse(
        checkin_id=checkin.id,
        status=checkin.status.value,
        opening_message=result["reply"],
    )


@router.post("/deep_mode_message", response_model=DeepModeMessageResponse)
async def deep_mode_message(
    request: DeepModeMessageRequest,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Send a message in the deep mode discussion flow."""
    checkin = db.query(CheckIn).filter(
        CheckIn.id == request.checkin_id,
        CheckIn.user_id == current_user.id,
    ).first()

    if not checkin:
        raise HTTPException(status_code=404, detail="Session not found")

    if checkin.status == CheckInStatus.completed:
        raise HTTPException(status_code=400, detail="This session is already completed")

    result = await process_message(
        checkin=checkin,
        user_message=request.message,
        db=db,
        angle=request.angle,
    )

    return DeepModeMessageResponse(
        reply=result["reply"],
        status=result["status"].value,
        draft=result.get("draft") or "",
        has_draft=result.get("draft") is not None,
    )


@router.post("/confirm_and_publish", response_model=ConfirmPublishResponse)
async def confirm_and_publish(
    request: ConfirmPublishRequest,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Confirm content and publish. Updates streak and points."""
    checkin = db.query(CheckIn).filter(
        CheckIn.id == request.checkin_id,
        CheckIn.user_id == current_user.id,
    ).first()

    if not checkin:
        raise HTTPException(status_code=404, detail="Session not found")

    # If not yet at draft_ready, force the content and move to pending
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending):
        checkin.content = request.content
        checkin.status = CheckInStatus.draft_ready
        db.commit()

    try:
        await confirm_content(checkin, request.content, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    try:
        result = await confirm_publish(checkin, db, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    return ConfirmPublishResponse(
        streak=result["streak"],
        points_earned=result["points_earned"],
        total_points=result["total_points"],
        level=result["level"],
        message=result["message"],
        newly_unlocked=result.get("newly_unlocked", []),
    )


@router.get("/user_stats", response_model=UserStatsResponse)
async def get_user_stats(
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Return user streak, points, level, and today's completion status."""
    today = get_today_cst()
    today_checkin = db.query(CheckIn).filter(
        CheckIn.user_id == current_user.id,
        CheckIn.date == today,
        CheckIn.status == CheckInStatus.completed,
    ).first()

    achievements = [
        {"type": a.achievement_type, "unlocked_at": str(a.unlocked_at)}
        for a in current_user.achievements
    ]

    return UserStatsResponse(
        streak=current_user.streak,
        longest_streak=current_user.longest_streak,
        points=current_user.points,
        level=current_user.level,
        diamonds=current_user.diamonds,
        today_completed=today_checkin is not None,
        achievements=achievements,
    )
