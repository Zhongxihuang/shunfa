from collections.abc import Generator

from fastapi import Depends, HTTPException, Request
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
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
    Resolve the DeepSeek API key for a user request using three-tier priority:
      1. X-User-Api-Key request header (highest priority)
      2. User's saved (encrypted) key in the database
      3. System environment key (only if REQUIRE_USER_API_KEY is false)
    """
    # 1. Request-level header
    header_key = request.headers.get("X-User-Api-Key", "").strip()
    if header_key:
        return header_key

    # 2. User-level stored key (encrypted in DB)
    if current_user.deepseek_api_key:
        try:
            from .utils.crypto import decrypt_api_key
            return decrypt_api_key(current_user.deepseek_api_key)
        except Exception:
            pass  # Decryption failure falls through to next tier

    # 3. Environment-level fallback
    if settings.deepseek_api_key and not settings.require_user_api_key:
        return settings.deepseek_api_key

    raise_api_error(
        status_code=400,
        error_code="missing_api_key",
        message="请在设置页面配置您的 DeepSeek API Key（https://platform.deepseek.com/api_keys）",
    )
