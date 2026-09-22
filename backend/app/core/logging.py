import json
import logging
import sys
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional


class StructuredFormatter(logging.Formatter):
    """Formats log records as structured key-value JSON messages, suppressing sensitive tokens."""

    SENSITIVE_PATTERNS = [
        "password",
        "secret",
        "token",
        "key",
        "credential",
    ]

    def format(self, record: logging.LogRecord) -> str:
        timestamp = self.formatTime(record, self.datefmt or "%Y-%m-%d %H:%M:%S")
        payload: Dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "name": record.name,
            "message": record.getMessage(),
        }

        # Include structured extra fields if present
        for key, value in record.__dict__.items():
            if not hasattr(logging.LogRecord, key) and key not in payload and not key.startswith("_"):
                # Mask credentials and sensitive keys
                if any(pat in key.lower() for pat in self.SENSITIVE_PATTERNS):
                    payload[key] = "********"
                else:
                    payload[key] = str(value)

        return json.dumps(payload)


def setup_logging() -> logging.Logger:
    """Configures application-wide structured logging."""
    from app.core.config import get_settings
    settings = get_settings()
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Replace existing handlers to ensure single structured formatter
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    root_logger.addHandler(handler)

    app_logger = logging.getLogger("autodba")
    app_logger.setLevel(log_level)
    return app_logger


logger = setup_logging()


@contextmanager
def log_operation(operation: str, logger_instance: Optional[logging.Logger] = None) -> Generator[Dict[str, Any], None, None]:
    """Context manager that logs operation lifecycle: start, success/failure, and elapsed duration."""
    target_logger = logger_instance or logger
    start_time = time.perf_counter()
    context: Dict[str, Any] = {"operation": operation, "status": "started"}
    target_logger.info(f"Starting {operation}", extra=context)

    try:
        yield context
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        context["status"] = "success"
        context["duration_ms"] = duration_ms
        target_logger.info(f"Completed {operation}", extra=context)
    except Exception as exc:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        context["status"] = "failed"
        context["duration_ms"] = duration_ms
        context["error_type"] = type(exc).__name__
        target_logger.error(f"Failed {operation}: {exc}", extra=context)
        raise
