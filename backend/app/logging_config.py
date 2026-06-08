import logging
import sys
import traceback
from contextvars import ContextVar
from datetime import UTC, datetime

# Per-task/coroutine request context for request ID (thread- and async-safe)
_request_id_context: ContextVar[str | None] = ContextVar('request_id', default=None)


class RequestIDFilter(logging.Filter):
    """Add request_id to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_context.get() or "-"
        return True


def setup_logging(level: str = "INFO") -> None:
    """Configure structured logging with request ID support."""

    class StructuredFormatter(logging.Formatter):
        """Human-readable format with request ID."""

        def format(self, record: logging.LogRecord) -> str:
            timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
            request_id = getattr(record, "request_id", "-")
            level = record.levelname
            name = record.name
            message = record.getMessage()

            parts = [f"[{timestamp}]"]
            if request_id and request_id != "-":
                parts.append(f"[{request_id[:8]}]")
            parts.append(f"[{level}]")
            parts.append(f"[{name}]")
            parts.append(message)

            result = " ".join(parts)

            # Add exception traceback if present
            if record.exc_info:
                result += "\n" + "".join(traceback.format_exception(*record.exc_info))

            return result

    # Root logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Console handler with structured format
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(StructuredFormatter())
    console_handler.addFilter(RequestIDFilter())
    root_logger.addHandler(console_handler)

    # Set levels for noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def set_request_id(request_id: str | None) -> None:
    """Set the request ID for the current context (coroutine/task-local)."""
    _request_id_context.set(request_id)


def get_logger(name: str) -> logging.Logger:
    """Get a logger with the given name."""
    return logging.getLogger(name)
