from __future__ import annotations

import json
import logging

from app.logging_config import SafeStructuredFormatter, configure_structured_logging


def test_safe_structured_formatter_redacts_sensitive_fields() -> None:
    formatter = SafeStructuredFormatter()
    logger = logging.getLogger("tests.logging")
    record = logger.makeRecord(
        name="tests.logging",
        level=logging.INFO,
        fn=__file__,
        lno=10,
        msg="chat_request_completed",
        args=(),
        exc_info=None,
        extra={
            "event": "chat_request_completed",
            "route": "tech_support",
            "user_id": "user_123",
            "latest_user_message": "my serial number is 111",
            "payload": {
                "authorization": "Bearer abc",
                "conversation_id": "conv_1000",
            },
        },
    )

    payload = json.loads(formatter.format(record))

    assert payload["event"] == "chat_request_completed"
    assert payload["route"] == "tech_support"
    assert payload["user_id"] == "[REDACTED]"
    assert payload["latest_user_message"] == "[REDACTED]"
    assert payload["payload"]["authorization"] == "[REDACTED]"
    assert payload["payload"]["conversation_id"] == "conv_1000"


def test_safe_structured_formatter_truncates_long_values() -> None:
    formatter = SafeStructuredFormatter()
    logger = logging.getLogger("tests.logging")
    record = logger.makeRecord(
        name="tests.logging",
        level=logging.INFO,
        fn=__file__,
        lno=30,
        msg="event_name",
        args=(),
        exc_info=None,
        extra={"details": "x" * 1000},
    )

    payload = json.loads(formatter.format(record))

    assert payload["details"].endswith("...<truncated>")


def test_safe_structured_formatter_preserves_payload_user_identifier() -> None:
    formatter = SafeStructuredFormatter()
    logger = logging.getLogger("tests.logging")
    record = logger.makeRecord(
        name="tests.logging",
        level=logging.INFO,
        fn=__file__,
        lno=40,
        msg="chat_request_received",
        args=(),
        exc_info=None,
        extra={
            "event": "chat_request_received",
            "payload_user_identifier": "user_login_001",
            "login_attempt": True,
        },
    )

    payload = json.loads(formatter.format(record))

    assert payload["payload_user_identifier"] == "user_login_001"
    assert payload["login_attempt"] is True


def test_configure_structured_logging_attaches_json_formatter() -> None:
    configure_structured_logging("info")
    root_logger = logging.getLogger()

    assert root_logger.level == logging.INFO
    assert root_logger.handlers
    assert isinstance(root_logger.handlers[0].formatter, SafeStructuredFormatter)
