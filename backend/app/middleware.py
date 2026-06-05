import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from .logging_config import get_logger, set_request_id

logger = get_logger("middleware")


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Middleware that generates and propagates a request ID."""

    async def dispatch(self, request: Request, call_next) -> Response:
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store in logging context
        set_request_id(request_id)

        # Add to response headers
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id

        return response


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware that logs all incoming requests and responses."""

    async def dispatch(self, request: Request, call_next) -> Response:
        import time

        from .logging_config import get_logger

        logger = get_logger("http.request")

        method = request.method
        path = request.url.path

        # Skip logging for health checks
        if path == "/health":
            return await call_next(request)

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            logger.info(
                f"{method} {path} - {response.status_code} - {duration_ms:.1f}ms"
            )

            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"{method} {path} - 500 - {duration_ms:.1f}ms - EXCEPTION: {type(e).__name__}"
            )
            raise
