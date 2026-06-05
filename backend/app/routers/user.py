from datetime import UTC, date, datetime, timedelta

import bcrypt
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from jose import jwt
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..dependencies import get_admin_user, get_current_user, get_db
from ..models import CheckIn, User
from ..rate_limit import limiter
from ..schemas import (
    AchievementItem,
    AchievementsResponse,
    ApiKeyStatusResponse,
    LoginRequest,
    LoginResponse,
    RegisterRequest,
    SaveApiKeyRequest,
    UserStatusResponse,
    WebAuthLoginRequest,
    WebLoginRequest,
)
from ..services.reminder_service import check_reminder_needed
from ..utils.time_utils import get_today_cst

router = APIRouter()


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _dev_wechat_openid() -> str:
    return "wx_dev_user"


async def get_wechat_openid(code: str) -> str:
    """Exchange a WeChat mini program login code for an openid.

    Local development often runs without WeChat credentials. In that case we
    use a stable dev openid so the restored mini program can run end-to-end.
    """
    if not settings.wechat_app_id or not settings.wechat_app_secret:
        if settings.environment == "production":
            raise HTTPException(status_code=503, detail="WeChat login is not configured")
        return _dev_wechat_openid()

    url = "https://api.weixin.qq.com/sns/jscode2session"
    params = {
        "appid": settings.wechat_app_id,
        "secret": settings.wechat_app_secret,
        "js_code": code,
        "grant_type": "authorization_code",
    }
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError, ValueError) as exc:
        if settings.environment != "production":
            return _dev_wechat_openid()
        raise HTTPException(status_code=503, detail="WeChat service unavailable") from exc

    if "errcode" in data and data["errcode"] != 0:
        if settings.environment != "production":
            return _dev_wechat_openid()
        raise HTTPException(
            status_code=400, detail=f"WeChat error: {data.get('errmsg', 'Unknown error')}"
        )

    openid = data.get("openid")
    if not openid:
        if settings.environment != "production":
            return _dev_wechat_openid()
        raise HTTPException(status_code=400, detail="Failed to get openid from WeChat")

    return openid


def create_jwt_token(user_id: int, token_version: int = 0) -> str:
    expire = datetime.now(UTC) + timedelta(hours=settings.jwt_expire_hours)
    payload = {"sub": str(user_id), "tv": token_version, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def get_user_today_status(user: User, today: date, db: Session) -> bool:
    """Check if user has completed today's check-in."""
    from ..models import CheckInStatus

    checkin = (
        db.query(CheckIn)
        .filter(
            CheckIn.user_id == user.id,
            CheckIn.date == today,
            CheckIn.status == CheckInStatus.completed,
        )
        .first()
    )
    return checkin is not None


def _build_login_response(user: User, today: date, db: Session) -> LoginResponse:
    token = create_jwt_token(user.id, user.token_version)
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
        reminder_needed=check_reminder_needed(user, db),
    )
    return LoginResponse(token=token, user=user_status)


def _safe_api_key_preview(plaintext: str) -> str | None:
    key = plaintext.strip()
    if len(key) < 12:
        return None
    return f"...{key[-4:]}"


# ── WeChat mini program login ─────────────────────────────────────────────────


@router.post("/login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    openid = await get_wechat_openid(body.code)

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

    return _build_login_response(user, get_today_cst(), db)


# ── Web auth: register + login ─────────────────────────────────────────────────


@router.post("/register", response_model=LoginResponse)
@limiter.limit("5/minute")
async def register(request: Request, body: RegisterRequest, db: Session = Depends(get_db)):
    """Register a new web user with username + password."""
    existing = db.query(User).filter(User.username == body.username).first()
    if existing:
        raise HTTPException(status_code=400, detail="用户名已存在")

    openid = f"web_{body.username}"
    if db.query(User).filter(User.openid == openid).first():
        raise HTTPException(status_code=400, detail="用户名已存在")

    try:
        user = User(
            openid=openid,
            username=body.username,
            password_hash=_hash_password(body.password),
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail="用户名已存在") from exc

    return _build_login_response(user, get_today_cst(), db)


@router.post("/auth_login", response_model=LoginResponse)
@limiter.limit("10/minute")
async def auth_login(request: Request, body: WebAuthLoginRequest, db: Session = Depends(get_db)):
    """Login with username + password (web users)."""
    user = db.query(User).filter(User.username == body.username).first()
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    if not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    return _build_login_response(user, get_today_cst(), db)


@router.post("/web_login", response_model=LoginResponse)
@limiter.limit("30/minute")
async def web_login(request: Request, body: WebLoginRequest, db: Session = Depends(get_db)):
    """Legacy single-password admin login. Kept for backward compatibility."""
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="Web login is not configured")
    if body.password != settings.admin_password:
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

    return _build_login_response(user, get_today_cst(), db)


# ── User API Key management ────────────────────────────────────────────────────


@router.get("/user/api_key/status", response_model=ApiKeyStatusResponse)
async def get_api_key_status(current_user: User = Depends(get_current_user)):
    """Check if the user has a DeepSeek API key configured (never returns the plaintext key)."""
    if not current_user.deepseek_api_key:
        return ApiKeyStatusResponse(configured=False)
    try:
        from ..utils.crypto import decrypt_api_key

        plaintext = decrypt_api_key(current_user.deepseek_api_key)
        preview = _safe_api_key_preview(plaintext)
        return ApiKeyStatusResponse(configured=True, preview=preview)
    except Exception:
        return ApiKeyStatusResponse(configured=True, preview=None)


@router.post("/user/api_key", response_model=ApiKeyStatusResponse)
async def save_api_key(
    request: SaveApiKeyRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Save the user's DeepSeek API key (stored encrypted)."""
    from ..utils.crypto import encrypt_api_key

    current_user.deepseek_api_key = encrypt_api_key(request.api_key.strip())
    db.commit()
    preview = _safe_api_key_preview(request.api_key)
    return ApiKeyStatusResponse(configured=True, preview=preview)


@router.delete("/user/api_key", response_model=ApiKeyStatusResponse)
async def delete_api_key(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Remove the user's saved DeepSeek API key."""
    current_user.deepseek_api_key = None
    db.commit()
    return ApiKeyStatusResponse(configured=False)


# ── User status + achievements ─────────────────────────────────────────────────


@router.get("/achievements", response_model=AchievementsResponse)
async def get_achievements(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    from ..services.achievement_service import get_user_achievements

    items = get_user_achievements(current_user)
    return AchievementsResponse(
        achievements=[AchievementItem(**i) for i in items], total=len(items)
    )


@router.get("/user_status", response_model=UserStatusResponse)
async def get_user_status(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
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
        reminder_needed=check_reminder_needed(current_user, db),
    )


# ── Admin: token revocation ────────────────────────────────────────────────────


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
    db: Session = Depends(get_db),
):
    """Admin endpoint to revoke a user's tokens. Rate limited to 5/minute."""
    user = db.query(User).filter(User.id == revoke_req.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.token_version += 1
    db.commit()

    return RevokeTokenResponse(revoked_user_id=user.id, new_token_version=user.token_version)
