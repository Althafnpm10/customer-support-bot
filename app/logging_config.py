from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

_REDACTED = "[REDACTED]"
_MAX_STRING_LENGTH = 512

_SENSITIVE_EXACT_KEYS = {
    "user_id",
    "message",
    "messages",
    "content",
    "latest_user_message",
    "response",
    "prompt",
}

_SENSITIVE_PARTIAL_TOKENS = (
    "authorization",
    "password",
    "secret",
    "token",
    "api_key",
    "access_key",
    "private_key",
    "secret_key",
)

_LOG_RECORD_RESERVED_FIELDS = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in _SENSITIVE_EXACT_KEYS or any(
        token in normalized for token in _SENSITIVE_PARTIAL_TOKENS
    )


def _truncate(value: str, *, limit: int = _MAX_STRING_LENGTH) -> str:
    if len(value) <= limit:
        return value
    return f"{value[:limit]}...<truncated>"


def _sanitize_value(value: Any, *, key: str | None = None) -> Any:
    if key and _is_sensitive_key(key):
        return _REDACTED

    if isinstance(value, dict):
        return {str(k): _sanitize_value(v, key=str(k)) for k, v in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]

    if isinstance(value, str):
        return _truncate(value)

    if isinstance(value, (bool, int, float)) or value is None:
        return value

    return _truncate(str(value))


class SafeStructuredFormatter(logging.Formatter):
    """Formats logs as JSON and redacts sensitive fields from extra payloads."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": _truncate(record.getMessage()),
            "event": getattr(record, "event", record.getMessage()),
        }

        for key, value in record.__dict__.items():
            if key in _LOG_RECORD_RESERVED_FIELDS or key.startswith("_"):
                continue
            payload[key] = _sanitize_value(value, key=key)

        if record.exc_info:
            payload["exception"] = _truncate(self.formatException(record.exc_info), limit=2048)

        return json.dumps(payload, ensure_ascii=True, separators=(",", ":"))


def configure_structured_logging(log_level: str) -> None:
    level = getattr(logging, (log_level or "info").upper(), logging.INFO)

    handler = logging.StreamHandler()
    handler.setFormatter(SafeStructuredFormatter())

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(handler)
    root_logger.setLevel(level)
