from datetime import UTC, date, datetime, timedelta

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import get_admin_user, get_current_user, get_db
from ..models import CheckIn, User
from ..rate_limit import limiter
from ..schemas import (
    AchievementItem,
    AchievementsResponse,
    LoginRequest,
    LoginResponse,
    UserStatusResponse,
    WebLoginRequest,
)
from ..services.reminder_service import check_reminder_needed
from ..utils.time_utils import get_today_cst

router = APIRouter()


async def get_wechat_openid(code: str) -> str:
    """Exchange WeChat login code for openid."""
    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "js_code": code,
        "grant_type": "authorization_code"
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError):
        raise HTTPException(status_code=503, detail="WeChat service unavailable")

    if "errcode" in data and data["errcode"] != 0:
        raise HTTPException(status_code=400, detail=f"WeChat error: {data.get('errmsg', 'Unknown error')}")

    openid = data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="Failed to get openid from WeChat")

    return openid


def create_jwt_token(user_id: int, token_version: int = 0) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": str(user_id), "tv": token_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_user_today_status(user: User, today: date, db: Session) -> bool:
    """Check if user has completed today's check-in."""
    from ..models import CheckInStatus
    checkin = db.query(CheckIn).filter(
        CheckIn.user_id == user.id,
        CheckIn.date == today,
        CheckIn.status == CheckInStatus.completed
    ).first()
    return checkin is not None


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    openid = await get_wechat_openid(request.code)

    # Get or create user
    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        try:
            user = User(openid=openid)
            db.add(user)
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.openid == openid).first()

    token = create_jwt_token(user.id, user.token_version)
    today = get_today_cst()

    user_status = UserStatusResponse(
        id=user.id,
        streak=user.streak,
        longest_streak=user.longest_streak,
        points=user.points,
        level=user.level,
        diamonds=user.diamonds,
        reminder_time=user.reminder_time,
        reminder_enabled=user.reminder_enabled,
        last_checkin_date=user.last_checkin_date,
        today_completed=get_user_today_status(user, today, db),
        reminder_needed=check_reminder_needed(user, db)
    )

    return LoginResponse(token=token, user=user_status)


@router.post("/web_login", response_model=LoginResponse)
async def web_login(request: WebLoginRequest, db: Session = Depends(get_db)):
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="Web login is not configured")
    if request.password != settings.admin_password:
        raise HTTPException(status_code=401, detail="Invalid password")

    openid = "web_admin"
    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        try:
            user = User(openid=openid)
            db.add(user)
            db.commit()
            db.refresh(user)
        except IntegrityError:
            db.rollback()
            user = db.query(User).filter(User.openid == openid).first()

    token = create_jwt_token(user.id, user.token_version)
    today = get_today_cst()

    user_status = UserStatusResponse(
        id=user.id,
        streak=user.streak,
        longest_streak=user.longest_streak,
        points=user.points,
        level=user.level,
        diamonds=user.diamonds,
        reminder_time=user.reminder_time,
        reminder_enabled=user.reminder_enabled,
        last_checkin_date=user.last_checkin_date,
        today_completed=get_user_today_status(user, today, db),
        reminder_needed=check_reminder_needed(user, db)
    )

    return LoginResponse(token=token, user=user_status)


@router.get("/achievements", response_model=AchievementsResponse)
async def get_achievements(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """获取用户已解锁的成就列表。"""
    from ..services.achievement_service import get_user_achievements
    items = get_user_achievements(current_user)
    return AchievementsResponse(
        achievements=[AchievementItem(**i) for i in items],
        total=len(items)
    )


@router.get("/user_status", response_model=UserStatusResponse)
async def get_user_status(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    today = get_today_cst()
    return UserStatusResponse(
        id=current_user.id,
        streak=current_user.streak,
        longest_streak=current_user.longest_streak,
        points=current_user.points,
        level=current_user.level,
        diamonds=current_user.diamonds,
        reminder_time=current_user.reminder_time,
        reminder_enabled=current_user.reminder_enabled,
        last_checkin_date=current_user.last_checkin_date,
        today_completed=get_user_today_status(current_user, today, db),
        reminder_needed=check_reminder_needed(current_user, db)
    )


from pydantic import BaseModel


class RevokeTokenRequest(BaseModel):
    user_id: int


class RevokeTokenResponse(BaseModel):
    revoked_user_id: int
    new_token_version: int


@router.post("/revoke_token", response_model=RevokeTokenResponse)
@limiter.limit("5/minute")
async def revoke_token(
    request: Request,
    revoke_req: RevokeTokenRequest,
    current_user: User = Depends(get_admin_user),
    db: Session = Depends(get_db)
):
    """Admin endpoint to revoke a user's tokens by incrementing their token_version.
    Requires admin JWT auth (web_admin user). Rate limited to 5/minute."""
    user = db.query(User).filter(User.id == revoke_req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.token_version += 1
    db.commit()

    return RevokeTokenResponse(
        revoked_user_id=user.id,
        new_token_version=user.token_version
    )
