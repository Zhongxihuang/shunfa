"""Coze plugin API router.

These endpoints are called by Coze workflows as plugin actions.
Requests may include a Feishu user id header; when missing, the backend
falls back to compatible identity headers or an anonymous Coze user.

Endpoint prefix: /api/coze/
Auth: X-Coze-Plugin-Token header (shared secret) + optional user identity headers
"""

import hmac
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import get_db
from ..rate_limit import limiter
from ..models import CheckIn, CheckInStatus, User
from ..services.content_service import confirm_publish
from ..services.discussion_service import (
    AUTO_SUGGEST_SENTINEL,
    process_message,
    reset_checkin_for_new_topic,
)
from ..services.draft_service import (
    confirm_content,
    quick_generate,
)
from ..services.local_hot_topic_store import ensure_topics_for_date, records_are_fallback
from ..utils.time_utils import get_today_cst

router = APIRouter(prefix="/coze")

ANONYMOUS_COZE_USER = "anonymous"
_VALID_ID_PATTERN = re.compile(r'^[\w\-\.@]{3,128}$')

USER_HEADER_PREFIXES = (
    ("X-Lark-User-Id", "feishu_user"),
    ("X-User-Id", "feishu_user"),
    ("X-Feishu-Open-Id", "feishu_openid"),
    ("X-Lark-Open-Id", "feishu_openid"),
    ("X-Open-Id", "feishu_openid"),
    ("X-Coze-Conversation-Id", "coze_conversation"),
    ("X-Conversation-Id", "coze_conversation"),
    ("X-Coze-Chat-Id", "coze_chat"),
    ("X-Chat-Id", "coze_chat"),
    ("X-Request-Id", "coze_request"),
)


# ── Auth ──────────────────────────────────────────────────────────────────────


def _validate_user_id(value: str) -> bool:
    return bool(_VALID_ID_PATTERN.match(value))


def _resolve_user_identity(request: Request, explicit_user_id: str | None) -> str | None:
    if explicit_user_id:
        stripped = explicit_user_id.strip()
        if stripped and _validate_user_id(stripped):
            return f"feishu_user:{stripped}"

    for header_name, prefix in USER_HEADER_PREFIXES:
        value = request.headers.get(header_name)
        if value:
            stripped = value.strip()
            if stripped and _validate_user_id(stripped):
                return f"{prefix}:{stripped}"

    return f"coze_anonymous:{ANONYMOUS_COZE_USER}"


def get_coze_user(
    request: Request,
    x_feishu_user_id: str | None = Header(None, alias="X-Feishu-User-Id"),
    x_coze_plugin_token: str = Header(..., alias="X-Coze-Plugin-Token"),
    db: Session = Depends(get_db),
) -> User:
    """Extract Feishu user ID from Coze request headers and look up/create User."""
    if not settings.enable_coze_plugin:
        raise HTTPException(status_code=404, detail="Coze plugin is disabled")
    if not settings.coze_plugin_token:
        raise HTTPException(status_code=503, detail="Plugin auth is not configured")
    # Constant-time comparison: a plain `!=` short-circuits on the first
    # differing byte, leaking the shared secret one character at a time to a
    # timing attacker. compare_digest takes the same time regardless of where
    # the strings diverge.
    if not hmac.compare_digest(x_coze_plugin_token, settings.coze_plugin_token):
        raise HTTPException(status_code=401, detail="Invalid plugin token")

    openid = _resolve_user_identity(request, x_feishu_user_id)
    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        user = User(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ── Request / Response models ─────────────────────────────────────────────────


class GetHotTopicsResponse(BaseModel):
    topics: list[dict]
    date: str
    # True when topics are synthetic backups (no real hot topics loaded yet).
    # Push consumers (WeChat daily push etc.) should surface this so users
    # don't see evergreen placeholders labelled as "today's hot topic".
    is_fallback: bool = False


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
    newly_unlocked: list[dict] = []


class UserStatsResponse(BaseModel):
    streak: int
    longest_streak: int
    points: int
    level: int
    diamonds: int
    today_completed: bool
    achievements: list[dict] = []


# ── Endpoints ─────────────────────────────────────────────────────────────────


@router.get("/get_hot_topics", response_model=GetHotTopicsResponse)
async def get_hot_topics(
    limit: int = 3,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Return locally stored hot topics for the daily push."""
    try:
        topic_date = get_today_cst()
        topics = ensure_topics_for_date(topic_date=topic_date, limit=limit, db=db)
    except Exception:
        topic_date = get_today_cst()
        topics = []

    topic_list = [
        {
            "index": i + 1,
            "hot_topic": t.title,
            "hot_source": t.source,
            "hot_url": t.url,
            "hot_summary": t.summary or "",
            "ai_angle": t.ai_angle or "",
            "ai_counter_angle": t.ai_counter_angle or "",
            "score": t.score,
            "category": t.category,
            "record_id": str(t.id),
        }
        for i, t in enumerate(topics)
    ]

    return GetHotTopicsResponse(
        topics=topic_list,
        date=topic_date.isoformat(),
        is_fallback=records_are_fallback(topics),
    )


@router.post("/quick_generate", response_model=QuickGeneratePluginResponse)
@limiter.limit(settings.generation_rate_limit)
async def coze_quick_generate(
    request: Request,
    body: QuickGeneratePluginRequest,
    current_user: User = Depends(get_coze_user),
):
    """Quick mode: generate content from hot topic + angle in ~30s. Stateless."""
    result = await quick_generate(
        hot_topic=body.hot_topic,
        angle=body.angle,
        platform=body.platform,
    )
    return QuickGeneratePluginResponse(**result)


@router.post("/start_deep_mode", response_model=StartDeepModeResponse)
@limiter.limit(settings.generation_rate_limit)
async def start_deep_mode(
    request: Request,
    body: StartDeepModeRequest,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Create a deep mode CheckIn session. Returns checkin_id for subsequent messages."""
    today = get_today_cst()

    # Reuse existing incomplete checkin for today, or create new one
    existing = (
        db.query(CheckIn)
        .filter(
            CheckIn.user_id == current_user.id,
            CheckIn.date == today,
            CheckIn.status != CheckInStatus.completed,
        )
        .first()
    )

    if existing:
        checkin = existing
        reset_checkin_for_new_topic(checkin, body.hot_topic, CheckInStatus.discussing)
        db.commit()
    else:
        checkin = CheckIn(
            user_id=current_user.id,
            date=today,
            topic=body.hot_topic,
            status=CheckInStatus.discussing,
        )
        db.add(checkin)
        db.commit()
        db.refresh(checkin)

    # Generate opening angle suggestions
    result = await process_message(
        checkin=checkin,
        user_message=AUTO_SUGGEST_SENTINEL,
        db=db,
        angle=body.angle,
    )

    return StartDeepModeResponse(
        checkin_id=checkin.id,
        status=checkin.status.value,
        opening_message=result["reply"],
    )


@router.post("/deep_mode_message", response_model=DeepModeMessageResponse)
@limiter.limit(settings.generation_rate_limit)
async def deep_mode_message(
    request: Request,
    body: DeepModeMessageRequest,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Send a message in the deep mode discussion flow."""
    checkin = (
        db.query(CheckIn)
        .filter(
            CheckIn.id == body.checkin_id,
            CheckIn.user_id == current_user.id,
        )
        .first()
    )

    if not checkin:
        raise HTTPException(status_code=404, detail="Session not found")

    if checkin.status == CheckInStatus.completed:
        raise HTTPException(status_code=400, detail="This session is already completed")

    result = await process_message(
        checkin=checkin,
        user_message=body.message,
        db=db,
        angle=body.angle,
    )

    return DeepModeMessageResponse(
        reply=result["reply"],
        status=result["status"].value,
        draft=result.get("draft") or "",
        has_draft=result.get("draft") is not None,
    )


@router.post("/confirm_and_publish", response_model=ConfirmPublishResponse)
@limiter.limit(settings.publish_rate_limit)
async def confirm_and_publish(
    request: Request,
    body: ConfirmPublishRequest,
    current_user: User = Depends(get_coze_user),
    db: Session = Depends(get_db),
):
    """Confirm content and publish. Updates streak and points."""
    checkin = (
        db.query(CheckIn)
        .filter(
            CheckIn.id == body.checkin_id,
            CheckIn.user_id == current_user.id,
        )
        .with_for_update()
        .first()
    )

    if not checkin:
        raise HTTPException(status_code=404, detail="Session not found")

    # If not yet at draft_ready, force the content and move to pending
    if checkin.status not in (CheckInStatus.draft_ready, CheckInStatus.pending):
        checkin.content = body.content
        checkin.status = CheckInStatus.draft_ready
        db.commit()

    try:
        await confirm_content(checkin, body.content, db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    try:
        result = await confirm_publish(checkin, db, current_user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

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
    today_checkin = (
        db.query(CheckIn)
        .filter(
            CheckIn.user_id == current_user.id,
            CheckIn.date == today,
            CheckIn.status == CheckInStatus.completed,
        )
        .first()
    )

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
