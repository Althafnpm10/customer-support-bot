from __future__ import annotations

from app.agents.customer_support import handle_customer_support
from app.services.mock_actions import build_default_tool_registry


def test_numeric_serial_follow_up_uses_existing_model_context() -> None:
    state = {
        "latest_user_message": "4545",
        "intent": "warranty_claim",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {
            "product_type": "camera",
            "model": "RX-100",
        },
    }

    result = handle_customer_support(state, build_default_tool_registry())
    hints = result["metadata"]["llm_hints"]

    assert result["extracted_entities"]["serial_number"] == "4545"
    assert hints["status"] == "warranty_details_required"
    assert hints["missing_fields"] == ["purchase_date"]


def test_alphanumeric_serial_with_hyphen_is_accepted() -> None:
    state = {
        "latest_user_message": "model name: RX-100, serial number: 45-45, purchase date: 2026-01-15",
        "intent": "warranty_claim",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {},
    }

    result = handle_customer_support(state, build_default_tool_registry())
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "warranty_initialized"
    active_request = result["shared_memory"]["customer_support"]["active_warranty_replacement"]
    assert active_request["serial_number"] == "45-45"
