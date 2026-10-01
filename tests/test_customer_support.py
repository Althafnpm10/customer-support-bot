from __future__ import annotations

from app.agents.customer_support import handle_customer_support
from app.services.mock_actions import build_default_tool_registry


def _base_state(message: str, *, intent: str = "warranty_claim") -> dict:
    return {
        "latest_user_message": message,
        "intent": intent,
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {},
    }


def test_asks_for_model_and_serial_for_warranty() -> None:
    result = handle_customer_support(
        _base_state("I want to claim warranty for my camera"),
        build_default_tool_registry(),
    )
    assert result["response"].startswith("Customer Support Agent:")
    assert "please enter the model name, serial number, purchase date" in result["response"].lower()
    assert "yyyy-mm-dd format" in result["response"].lower()
    assert "purchase date" in result["response"]
    assert result["tool_calls"] == []


def test_initializes_warranty_replacement_when_details_are_present() -> None:
    state = _base_state("model name: RX-100, serial number: 555001, purchase date: 2026-01-15")
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "warranty replacement initialized." in result["response"]
    assert result["tool_calls"] == []
    assert "model" not in result["extracted_entities"]
    assert "serial_number" not in result["extracted_entities"]
    assert "purchase_date" not in result["extracted_entities"]


def test_initializes_warranty_replacement_for_replacement_intent() -> None:
    state = _base_state(
        "Need replacement, model NO: X7 and SN: 8871, purchase date: 2026-01-10",
        intent="replacement_request",
    )
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "warranty replacement initialized." in result["response"]


def test_initializes_warranty_replacement_with_comma_separated_details() -> None:
    state = _base_state("sd20,6445,2025-04-05")
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "warranty replacement initialized." in result["response"]
    assert result["tool_calls"] == []


def test_prompts_only_for_purchase_date_when_model_and_serial_are_provided() -> None:
    state = _base_state("sd20 6445")
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "please enter the purchase date" in result["response"].lower()
    assert "yyyy-mm-dd format" in result["response"].lower()
    assert result["extracted_entities"]["model"] == "SD20"
    assert result["extracted_entities"]["serial_number"] == "6445"


def test_parses_freeform_product_name_and_serial_number() -> None:
    state = _base_state("Atlas CX100 Mirrorless Camera 8656")
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "please enter the purchase date" in result["response"].lower()
    assert result["extracted_entities"]["product_type"] == "camera"
    assert result["extracted_entities"]["model"] == "ATLAS CX100 MIRRORLESS CAMERA"
    assert result["extracted_entities"]["serial_number"] == "8656"


def test_detects_wifi_modem_product_type_for_warranty_context() -> None:
    result = handle_customer_support(
        _base_state("I want warranty for my wifi modem"),
        build_default_tool_registry(),
    )

    assert result["response"].startswith("Customer Support Agent:")
    assert "please enter the model name, serial number, purchase date" in result["response"].lower()
    assert result["extracted_entities"]["product_type"] == "wifi_modem"


def test_accepts_serial_with_alphabets() -> None:
    state = _base_state("model name: RX-100, serial number: SN-555-A, purchase date: 2026-01-15")
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "warranty replacement initialized." in result["response"].lower()


def test_requests_correct_details_when_serial_number_missing() -> None:
    state = _base_state("model name: RX-100, purchase date: 2026-01-15")
    result = handle_customer_support(state, build_default_tool_registry())

    assert result["response"].startswith("Customer Support Agent:")
    assert "give me correct details" in result["response"].lower()


def test_returns_expired_message_when_warranty_is_out_of_date() -> None:
    state = _base_state("model name: RX-100, serial number: 555001, purchase date: 2020-01-01")
    result = handle_customer_support(state, build_default_tool_registry())
    lower = result["response"].lower()

    assert result["response"].startswith("Customer Support Agent:")
    assert "warranty" in lower and "expired" in lower
    assert any(term in lower for term in ("buy", "new", "recommend", "upgrade", "replacement option"))


def test_returns_unsupported_item_message_for_out_of_scope_product() -> None:
    result = handle_customer_support(
        _base_state("I want warranty for my laptop"),
        build_default_tool_registry(),
    )

    assert result["response"].startswith("Customer Support Agent:")
    assert "sorry, we dont deal with laptop right now." in result["response"].lower()


def test_cancels_active_warranty_replacement_from_shared_memory() -> None:
    first = handle_customer_support(
        _base_state("model name: RX-100, serial number: 555001, purchase date: 2026-01-15"),
        build_default_tool_registry(),
    )
    assert "warranty replacement initialized." in first["response"].lower()

    second_state = _base_state(
        "do you remember the camera warranty replacement? cancel that as it started working",
        intent="cancel_request",
    )
    second_state["shared_memory"] = first.get("shared_memory", {})
    second_state["extracted_entities"] = first.get("extracted_entities", {})
    second = handle_customer_support(second_state, build_default_tool_registry())

    assert "canceled your warranty replacement request" in second["response"].lower()
    customer_memory = second["shared_memory"]["customer_support"]
    assert "active_warranty_replacement" not in customer_memory
    assert customer_memory["last_warranty_replacement"]["status"] == "cancelled"


def test_recalls_previous_warranty_replacement_details_from_shared_memory() -> None:
    first = handle_customer_support(
        _base_state("model name: RX-100, serial number: 555001, purchase date: 2026-01-15"),
        build_default_tool_registry(),
    )
    assert "warranty replacement initialized." in first["response"].lower()

    second_state = _base_state("do you remember the camera that i asked for warranty replacement?")
    second_state["shared_memory"] = first.get("shared_memory", {})
    second = handle_customer_support(second_state, build_default_tool_registry())

    assert "yes, i remember your warranty replacement request" in second["response"].lower()
    assert "rx-100" in second["response"].lower()
    assert "555001" in second["response"]
    assert "2026-01-15" in second["response"]


def test_memory_question_without_previous_replacement_is_friendly() -> None:
    result = handle_customer_support(
        _base_state("do you remember the camera i asked warranty replacement for?"),
        build_default_tool_registry(),
    )

    assert result["response"].startswith("Customer Support Agent:")
    assert "could not find a previous warranty replacement request" in result["response"].lower()
