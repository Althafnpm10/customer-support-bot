from __future__ import annotations

from app.agents.customer_support import handle_customer_support
from app.services.mock_actions import build_default_tool_registry


def _state(message: str, *, intent: str = "warranty_claim") -> dict:
    return {
        "latest_user_message": message,
        "intent": intent,
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {},
    }


def test_warranty_expired_includes_recommended_products_for_llm() -> None:
    state = _state("model name: RX-100, serial number: 555001, purchase date: 2020-01-01")
    state["extracted_entities"] = {"product_type": "camera"}
    result = handle_customer_support(
        state,
        build_default_tool_registry(),
    )
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "warranty_expired"
    assert hints["escalate_to_sales"] is True
    assert hints["upsell_context"] is True
    assert hints["upsell_reason"] == "warranty_expired"
    assert isinstance(hints["recommended_products"], list)
    assert hints["recommended_products"]
    assert all("name" in product and "price" in product for product in hints["recommended_products"])
    assert all(product.get("category") == "camera" for product in hints["recommended_products"])


def test_non_eligible_replacement_includes_recommended_products_for_llm() -> None:
    result = handle_customer_support(
        _state("my camera is physically damaged and cannot issue replacement"),
        build_default_tool_registry(),
    )
    hints = result["metadata"]["llm_hints"]

    assert hints["status"] == "non_eligible_replacement_case"
    assert hints["escalate_to_sales"] is True
    assert hints["upsell_context"] is True
    assert hints["upsell_reason"] == "non_repairable_or_non_eligible"
    assert isinstance(hints["recommended_products"], list)
    assert hints["recommended_products"]
    assert all("name" in product and "price" in product for product in hints["recommended_products"])
    assert all(product.get("category") == "camera" for product in hints["recommended_products"])
