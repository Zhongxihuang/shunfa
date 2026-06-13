import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
from app.dependencies import get_db
from app.errors import normalize_http_error
from app.logging_config import get_logger, setup_logging
from app.middleware import RequestIDMiddleware, RequestLoggingMiddleware
from app.routers import (
    admin,
    analytics,
    content,
    coze_plugin,
    hot_topics,
    image_jobs,
    reminder,
    topics,
    user,
)
from app.routers.my import router as my_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup logging
    log_level = "DEBUG" if settings.environment == "development" else "INFO"
    setup_logging(log_level)
    logger = get_logger("main")
    logger.info(f"Starting 顺发 API in {settings.environment} mode")

    # Initialize Sentry if DSN is configured
    if os.getenv("SENTRY_DSN"):
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration

        def before_send(event, hint):
            request = event.get("request") or {}
            headers = request.get("headers") or {}
            for key in list(headers.keys()):
                if key.lower() in {"authorization", "x-user-api-key"}:
                    headers[key] = "[Filtered]"
            return event

        sentry_sdk.init(
            dsn=os.getenv("SENTRY_DSN"),
            integrations=[FastApiIntegration()],
            environment=settings.environment,
            traces_sample_rate=0.1,
            send_default_pii=False,
            before_send=before_send,
        )
        logger.info("Sentry initialized")

    # Development: auto-upgrade to latest migration
    if settings.environment == "development":
        from alembic.config import Config

        from alembic import command

        logger.debug("Running database migrations...")
        alembic_cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
        command.upgrade(alembic_cfg, "head")
        logger.info("Database migrations complete")

    yield
    logger.info("Shutting down 顺发 API")
    from app.services.render_service import shutdown_browser

    await shutdown_browser()


_is_prod = settings.environment == "production"
app = FastAPI(
    title="顺发 API",
    description="Gamified writing assistant backend",
    version="1.0.0",
    lifespan=lifespan,
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

# Prometheus /metrics endpoint. Keep it off by default and never expose it from
# production without an internal gateway.
if settings.enable_metrics and not _is_prod:
    instrumentator = Instrumentator(
        should_group_status_codes=False,
        should_ignore_untemplated=True,
        should_respect_env_var=False,
        should_instrument_requests_inprogress=True,
        excluded_handlers=["/health", "/metrics"],
        inprogress_name="shunfa_inprogress_requests",
        inprogress_labels=True,
    )
    instrumentator.instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

# Add middlewares
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.validate_cors(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-User-Api-Key", "X-Request-ID"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(RequestLoggingMiddleware)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(
        status_code=429,
        content={"detail": "请求过于频繁，请稍后再试"},
        headers={"Retry-After": str(exc.detail)},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=normalize_http_error(request, exc),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = request.headers.get("X-Request-ID")
    content = {
        "error_code": "validation_error",
        "message": "请求参数不正确",
    }
    if request_id:
        content["request_id"] = request_id
    return JSONResponse(status_code=422, content=content)


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch unhandled exceptions, log them, and return a safe error response."""
    from app.logging_config import _request_id_context, get_logger

    logger = get_logger("exception")
    request_id = _request_id_context.get() or "unknown"

    logger.exception(f"Unhandled exception: {type(exc).__name__}: {str(exc)}")

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Internal server error",
            "request_id": request_id,
        },
        headers={"X-Request-ID": request_id},
    )


# Register routers
app.include_router(topics.router, prefix="/api")
app.include_router(content.router, prefix="/api")
app.include_router(user.router, prefix="/api")
app.include_router(reminder.router, prefix="/api")
app.include_router(hot_topics.router, prefix="/api")
app.include_router(analytics.router, prefix="/api")
if settings.enable_coze_plugin:
    app.include_router(coze_plugin.router, prefix="/api")
app.include_router(my_router, prefix="/api")
app.include_router(image_jobs.router, prefix="/api")
app.include_router(admin.router)


@app.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """
    Enhanced health check including database connectivity.
    """
    checks = {"status": "ok", "version": app.version}

    # Check database connectivity
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
        checks["status"] = "degraded"

    return checks


@app.get("/")
async def root():
    return {"message": "顺发 API", "docs": "/docs"}
