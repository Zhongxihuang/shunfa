from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import httpx
from datetime import datetime, timedelta, date
from jose import jwt

from ..dependencies import get_db, get_current_user
from ..models import User
from ..schemas import LoginRequest, LoginResponse, UserStatusResponse
from ..config import settings
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
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        data = response.json()

    if "errcode" in data and data["errcode"] != 0:
        raise HTTPException(status_code=400, detail=f"WeChat error: {data.get('errmsg', 'Unknown error')}")

    openid = data.get("openid")
    if not openid:
        raise HTTPException(status_code=400, detail="Failed to get openid from WeChat")

    return openid


def create_jwt_token(user_id: int) -> str:
    expire = datetime.utcnow() + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": str(user_id), "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_user_today_status(user: User, today: date) -> bool:
    """Check if user has completed today's check-in."""
    from ..models import CheckInStatus
    if not user.checkins:
        return False
    today_checkins = [c for c in user.checkins if c.date == today]
    return any(c.status == CheckInStatus.completed for c in today_checkins)


@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    openid = await get_wechat_openid(request.code)

    # Get or create user
    user = db.query(User).filter(User.openid == openid).first()
    if not user:
        user = User(openid=openid)
        db.add(user)
        db.commit()
        db.refresh(user)

    token = create_jwt_token(user.id)
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
        today_completed=get_user_today_status(user, today)
    )

    return LoginResponse(token=token, user=user_status)


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
        today_completed=get_user_today_status(current_user, today)
    )
