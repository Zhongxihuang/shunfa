import logging
from collections.abc import Generator

from fastapi import Depends, HTTPException, Request

logger = logging.getLogger(__name__)
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .errors import raise_api_error

security = HTTPBearer()


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
        token_version = payload.get("tv", 0)
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    from .models import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.token_version != token_version:
        raise HTTPException(status_code=401, detail="Token has been revoked")

    return user


def get_admin_user(
    credentials: HTTPAuthorizationCredentials = Depends(security), db: Session = Depends(get_db)
):
    """Admin-only endpoint — requires valid JWT of the web_admin user."""
    token = credentials.credentials
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id = int(payload.get("sub"))
        token_version = payload.get("tv", 0)
    except (JWTError, ValueError, TypeError) as exc:
        raise HTTPException(status_code=401, detail="Invalid or expired token") from exc

    from .models import User

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if user.token_version != token_version:
        raise HTTPException(status_code=401, detail="Token has been revoked")
    if user.openid != "web_admin":
        raise HTTPException(status_code=403, detail="Admin access required")

    return user


async def get_resolved_api_key(
    request: Request,
    current_user=Depends(get_current_user),
) -> str:
    """
    Resolve the DeepSeek API key for a user request using a layered priority:
      1. X-User-Api-Key request header (highest priority)
      2. User's saved (encrypted) key in the database
      3. Free-trial shared key (while the user has free quota remaining)
      4. System environment key (only if REQUIRE_USER_API_KEY is false)

    The chosen source is recorded on `request.state.api_key_source` so the
    endpoint can decide whether to charge a free-quota credit after a
    successful generation.
    """
    from .services.free_quota import free_quota_enabled, free_quota_remaining

    # 1. Request-level header (a user pasting their own key per request)
    header_key = request.headers.get("X-User-Api-Key", "").strip()
    if header_key:
        request.state.api_key_source = "header"
        return header_key

    # 2. User-level stored key (encrypted in DB)
    if current_user.deepseek_api_key:
        try:
            from .utils.crypto import decrypt_api_key

            request.state.api_key_source = "user"
            return decrypt_api_key(current_user.deepseek_api_key)
        except Exception as e:
            logger.warning(
                "Failed to decrypt stored API key for user %s: %s. "
                "This may indicate API_KEY_ENCRYPTION_SECRET was rotated without migrating stored keys.",
                current_user.id,
                type(e).__name__,
            )

    # 3. Free-trial shared key — let new users taste the product before BYOK.
    if free_quota_enabled() and free_quota_remaining(current_user) > 0:
        request.state.api_key_source = "free_quota"
        return settings.deepseek_api_key  # type: ignore[return-value]

    # 4. Environment-level fallback (self-host / unlimited)
    if settings.deepseek_api_key and not settings.require_user_api_key:
        request.state.api_key_source = "system"
        return settings.deepseek_api_key

    # Exhausted: differentiate "free trial used up" from "never had a key" so the
    # frontend can show the right call-to-action and we can measure conversion.
    if free_quota_enabled():
        from .services.analytics import track

        track(
            "free_quota_exhausted",
            user_id=current_user.id,
            props={"limit": settings.free_quota_limit},
        )
        raise_api_error(
            status_code=400,
            error_code="free_quota_exhausted",
            message="你的免费体验额度已用完，请在设置页面配置自己的 DeepSeek API Key 继续使用"
            "（https://platform.deepseek.com/api_keys）。",
        )

    raise_api_error(
        status_code=400,
        error_code="missing_api_key",
        message="请在设置页面配置您的 DeepSeek API Key（https://platform.deepseek.com/api_keys）",
    )
