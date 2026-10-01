from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes import create_api_router
from app.config import Settings
from app.graph.nodes import NodeDependencies
from app.graph.workflow import build_support_workflow
from app.main import app
from app.services.knowledge_base import KnowledgeBaseService
from app.services.mock_actions import build_default_tool_registry
from app.services.response_generator import NoopResponseGenerator
from app.storage.conversation_store import InMemoryConversationStore


client = TestClient(app)


def test_storefront_page() -> None:
    response = client.get("/")
    assert response.status_code == 200
    assert "CU Electronics Store" in response.text
    assert "chat-toggle" in response.text


def test_health_endpoint() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_creates_new_conversation() -> None:
    response = client.post("/chat", json={"message": "My router keeps disconnecting"})
    body = response.json()
    assert response.status_code == 200
    assert body["conversation_id"].startswith("conv_")
    assert body["route"] == "tech_support"
    assert body["intent"] == "router_disconnect_issue"
    assert body["response"].startswith("Technical Support Agent:")
    assert isinstance(body["tool_calls"], list)
    assert body["metadata"]["greeted"] is True
    assert body["metadata"]["handoff_target"] == "technical_support_agent"


def test_chat_continues_existing_conversation() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: 555001, purchase date: 2026-01-15",
        },
    )
    body = second.json()
    assert second.status_code == 200
    assert body["conversation_id"] == conversation_id
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert body["response"].startswith("Customer Support Agent:")
    assert body["metadata"]["handoff_target"] == "customer_support_agent"
    assert "warranty replacement initialized." in body["response"]
    assert body["tool_calls"] == []


def test_chat_supports_independent_user_sessions() -> None:
    user_a = client.post("/chat", json={"user_id": "user_a", "message": "My router keeps disconnecting"}).json()
    user_b = client.post("/chat", json={"user_id": "user_b", "message": "I want to claim warranty for my camera"}).json()
    purchase_date = (datetime.now(UTC).date() - timedelta(days=100)).isoformat()

    assert user_a["conversation_id"] != user_b["conversation_id"]

    follow_a = client.post(
        "/chat",
        json={
            "conversation_id": user_a["conversation_id"],
            "user_id": "user_a",
            "message": "router slow speed now",
        },
    ).json()
    follow_b = client.post(
        "/chat",
        json={
            "conversation_id": user_b["conversation_id"],
            "user_id": "user_b",
            "message": f"My purchase date is {purchase_date}",
        },
    ).json()

    assert follow_a["conversation_id"] == user_a["conversation_id"]
    assert follow_b["conversation_id"] == user_b["conversation_id"]
    assert follow_a["route"] == "tech_support"
    assert follow_b["route"] == "customer_support"


def test_chat_greeting_returns_welcome_response() -> None:
    response = client.post("/chat", json={"message": "hello"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "fallback"
    assert body["intent"] == "greeting"
    assert "hello, how can i help you?" in body["response"].lower()


def test_chat_greeting_good_morning_is_mirrored() -> None:
    response = client.post("/chat", json={"message": "good morning"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "fallback"
    assert body["intent"] == "greeting"
    assert "good morning, how can i help you?" in body["response"].lower()


def test_warranty_follow_up_does_not_reuse_previous_model_and_serial() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: 555001, purchase date: 2026-01-15",
        },
    ).json()

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "I need a replacement",
        },
    ).json()

    assert second["intent"] == "warranty_claim"
    assert "warranty replacement initialized." in second["response"]
    assert third["route"] == "customer_support"
    assert third["intent"] == "replacement_request"
    assert "please enter the model name, serial number, purchase date" in third["response"].lower()
    assert "yyyy-mm-dd format" in third["response"].lower()


def test_chat_can_cancel_previous_warranty_replacement_using_shared_memory() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: 555001, purchase date: 2026-01-15",
        },
    ).json()
    assert "warranty replacement initialized." in second["response"].lower()

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": (
                "do you remember the camera that i asked for warranty replacement. "
                "i want to cancel that, as it started working."
            ),
        },
    ).json()

    assert third["route"] == "customer_support"
    assert third["intent"] == "cancel_request"
    assert "canceled your warranty replacement request" in third["response"].lower()
    assert "rx-100" in third["response"].lower()


def test_chat_can_recall_previous_warranty_replacement_details() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: 555001, purchase date: 2026-01-15",
        },
    ).json()
    assert "warranty replacement initialized." in second["response"].lower()

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "do you remember the camera that i asked for warranty replacement?",
        },
    ).json()

    assert third["route"] == "customer_support"
    assert third["intent"] == "warranty_claim"
    assert "yes, i remember your warranty replacement request" in third["response"].lower()
    assert "rx-100" in third["response"].lower()
    assert "555001" in third["response"]
    assert "2026-01-15" in third["response"]


def test_chat_returns_unsupported_item_message() -> None:
    response = client.post("/chat", json={"message": "My laptop fan is too loud"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "fallback"
    assert body["metadata"]["handoff_target"] == "support_triage_agent"
    assert "sorry, we dont deal with laptop right now." in body["response"].lower()


def test_chat_purchase_query_routes_to_sales_support() -> None:
    response = client.post("/chat", json={"message": "can i buy a cpu from this website?"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "order_placement"
    assert body["metadata"]["handoff_target"] == "sales_support_agent"
    assert "sales support agent:" in body["response"].lower()


def test_chat_routes_modem_issue_to_technical_support() -> None:
    response = client.post("/chat", json={"message": "my wifi modem loses sync frequently"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "tech_support"
    assert body["intent"] == "modem_sync_issue"
    assert "modem" in body["response"].lower()


def test_chat_recommends_wifi_modem_for_feature_query() -> None:
    response = client.post("/chat", json={"message": "i need a wifi modem with gigabit"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "feature_based_recommendation"
    assert "here is the wifi modem with gigabit" in body["response"].lower()
    assert "wavenet docsis 3.1 modem" in body["response"].lower()


def test_chat_unknown_query_returns_support_only_message() -> None:
    response = client.post("/chat", json={"message": "what is the weather today?"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "fallback"
    assert body["intent"] == "unknown"
    assert "how can i help you?" in body["response"].lower()


def test_chat_compares_two_products_in_sales_agent() -> None:
    response = client.post(
        "/chat",
        json={"message": "compare Atlas CX100 Mirrorless Camera vs Atlas Vlog Pro 4K"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "product_comparison"
    assert "atlas cx100 mirrorless camera" in body["response"].lower()
    assert "atlas vlog pro 4k" in body["response"].lower()
    assert "recommend" in body["response"].lower()


def test_chat_recommends_product_based_on_features() -> None:
    response = client.post(
        "/chat",
        json={"message": "find a suitable router with mesh coverage under $300"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "feature_based_recommendation"
    assert "here is the router with" in body["response"].lower()
    assert "aerolink mesh router kit" in body["response"].lower()
    assert "aerolink ax5400 router" not in body["response"].lower()


def test_chat_need_product_with_feature_routes_to_sales() -> None:
    response = client.post(
        "/chat",
        json={"message": "i need a camera with 4k"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "feature_based_recommendation"
    assert "here is the camera with 4k" in body["response"].lower()
    assert "atlas vlog pro 4k" in body["response"].lower()


def test_chat_places_order_after_user_selection() -> None:
    first = client.post(
        "/chat",
        json={"message": "find a suitable router with streaming under $250"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "place order for AeroLink AX5400 Router"},
    )
    second_body = second.json()

    assert second.status_code == 200
    assert second_body["route"] == "sales_support"
    assert second_body["intent"] == "order_placement"
    assert "street, city, state, and pin" in second_body["response"].lower()

    third = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 Market Street, San Francisco, CA 94105"},
    )
    third_body = third.json()

    assert third.status_code == 200
    assert third_body["route"] == "sales_support"
    assert "your order is placed" in third_body["response"].lower()
    assert "thank you for choosing us" in third_body["response"].lower()
    assert third_body["tool_calls"][-1]["tool_name"] == "place_mock_order"


def test_chat_can_cancel_order_using_shared_memory() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for AeroLink AX5400 Router"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 Market Street, San Francisco, CA 94105"},
    ).json()

    third = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "cancel my order"},
    )
    body = third.json()

    assert third.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "order_cancellation"
    assert "order cancellation is completed" in body["response"].lower()
    assert body["tool_calls"][-1]["tool_name"] == "cancel_mock_order"


def test_chat_can_cancel_order_by_reference_id() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for AeroLink AX5400 Router"},
    ).json()
    conversation_id = first["conversation_id"]
    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 Market Street, San Francisco, CA 94105"},
    ).json()
    order_reference = second["tool_calls"][-1]["reference_id"]

    third = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": f"cancel order {order_reference}"},
    )
    body = third.json()

    assert third.status_code == 200
    assert body["route"] == "sales_support"
    assert order_reference in body["response"]
    assert body["tool_calls"][-1]["tool_name"] == "cancel_mock_order"


def test_chat_cancell_this_order_phrase_cancels_recent() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for AeroLink AX5400 Router"},
    ).json()
    conversation_id = first["conversation_id"]
    client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 Market Street, San Francisco, CA 94105"},
    )

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "i need to cancell this order"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "order_cancellation"
    assert "order cancellation is completed" in body["response"].lower()
    assert body["tool_calls"][-1]["tool_name"] == "cancel_mock_order"


def test_chat_cancels_camera_order_by_model_name() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for Atlas CX100 Mirrorless Camera"},
    ).json()
    conversation_id = first["conversation_id"]
    client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 zsd palakkad kerala 678632"},
    )

    client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "place order for Atlas Vlog Pro 4K"},
    )
    client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "12 MG Road Bengaluru Karnataka 560001 India"},
    )

    cancel = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "i need to cancel the order of camera model cx100"},
    )
    body = cancel.json()

    assert cancel.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "order_cancellation"
    assert "atlas cx100 mirrorless camera" in body["response"].lower()
    assert "order cancellation is completed" in body["response"].lower()


def test_chat_understands_choose_phrase_in_comparison_context() -> None:
    first = client.post(
        "/chat",
        json={"message": "compare Atlas CX100 Mirrorless Camera vs Atlas Vlog Pro 4K"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "i choose atlas camera"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "order_placement"
    assert "street, city, state, and pin" in body["response"].lower()
    assert "atlas" in body["response"].lower()


def test_chat_understands_prefer_xeno_cpu_in_comparison_context() -> None:
    first = client.post(
        "/chat",
        json={"message": "compare ZenCore X8 Desktop CPU vs ZenCore X12 Creator CPU"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "i prefer xeno cpu"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "order_placement"
    assert "street, city, state, and pin" in body["response"].lower()
    assert "zencore" in body["response"].lower()


def test_chat_accepts_no_comma_address_with_pin() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for AeroLink AX5400 Router"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 Market Street San Francisco CA 94105"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert "your order is placed" in body["response"].lower()
    assert "45 Market Street, San Francisco, CA - 94105" in body["response"]
    assert body["tool_calls"][-1]["tool_name"] == "place_mock_order"


def test_chat_accepts_indian_address_without_commas() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for AeroLink AX5400 Router"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "12 MG Road Bengaluru Karnataka 560001 India"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert "your order is placed" in body["response"].lower()
    assert "12 MG Road, Bengaluru, Karnataka - 560001" in body["response"]
    assert body["tool_calls"][-1]["tool_name"] == "place_mock_order"
    assert "street:" not in body["response"].lower()


def test_chat_parses_mixed_numeric_alphabetic_street_without_commas() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for Atlas CX100 Mirrorless Camera"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "45 zsd palakkad kerala 678632"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert "your order is placed" in body["response"].lower()
    assert "45 zsd, Palakkad, Kerala - 678632" in body["response"]
    assert "street:" not in body["response"].lower()


def test_chat_generic_buy_camera_does_not_auto_order_previous_choice() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for Atlas CX100 Mirrorless Camera"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "i need to buy a camera"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert "your order is placed" not in body["response"].lower()
    assert "based on your requirements" in body["response"].lower()
    assert "atlas cx100 mirrorless camera" in body["response"].lower()
    assert "atlas vlog pro 4k" in body["response"].lower()


def test_chat_generic_buy_with_features_returns_recommendation_not_auto_order() -> None:
    first = client.post(
        "/chat",
        json={"message": "place order for Atlas CX100 Mirrorless Camera"},
    ).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={"conversation_id": conversation_id, "message": "i need to buy a camera with 4k and autofocus under $600"},
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "sales_support"
    assert "your order is placed" not in body["response"].lower()
    assert "here is the camera with" in body["response"].lower()
    assert "atlas vlog pro 4k" in body["response"].lower()
    assert "atlas cx100 mirrorless camera" not in body["response"].lower()


def test_chat_returns_only_cpu_with_8_cores_for_specific_feature_query() -> None:
    response = client.post(
        "/chat",
        json={"message": "i need a cpu with 8 cores"},
    )
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "sales_support"
    assert body["intent"] == "feature_based_recommendation"
    assert "here is the cpu with 8 cores" in body["response"].lower()
    assert "zencore x8 desktop cpu" in body["response"].lower()
    assert "zencore x12 creator cpu" not in body["response"].lower()


def test_chat_warranty_expired_message_includes_sales_convincing_text() -> None:
    first = client.post("/chat", json={"message": "issue warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: 555001, purchase date: 2020-01-01",
        },
    )
    body = second.json()
    lower = body["response"].lower()

    assert second.status_code == 200
    assert body["route"] == "customer_support"
    assert "warranty" in lower and "expired" in lower
    assert any(term in lower for term in ("buy", "new", "recommend", "upgrade", "replacement option"))
    assert ("atlas cx100 mirrorless camera" in lower) or ("atlas vlog pro 4k" in lower)


def test_chat_accepts_serial_with_alphabets_for_warranty() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: SN-555-A, purchase date: 2026-01-15",
        },
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    lower = body["response"].lower()
    assert "warranty" in lower and "initial" in lower


def test_chat_requests_correct_details_when_serial_number_missing() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, purchase date: 2026-01-15",
        },
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert "give me correct details" in body["response"].lower()


def test_chat_numeric_serial_follow_up_stays_in_customer_support() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100",
        },
    ).json()
    assert second["route"] == "customer_support"
    assert second["intent"] == "warranty_claim"

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "4545",
        },
    )
    body = third.json()
    lower = body["response"].lower()

    assert third.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert "purchase" in lower and "date" in lower


def test_chat_alphanumeric_serial_follow_up_stays_in_customer_support() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100",
        },
    ).json()
    assert second["route"] == "customer_support"
    assert second["intent"] == "warranty_claim"

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "SN-45A",
        },
    )
    body = third.json()
    lower = body["response"].lower()

    assert third.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert "purchase" in lower and "date" in lower


def test_chat_shows_warranty_expired_message() -> None:
    first = client.post("/chat", json={"message": "issue warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "model name: RX-100, serial number: 555001, purchase date: 2020-01-01",
        },
    )
    body = second.json()
    lower = body["response"].lower()

    assert second.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert "warranty" in lower and "expired" in lower
    assert any(term in lower for term in ("buy", "new", "recommend", "upgrade", "replacement option"))


def test_chat_accepts_comma_separated_warranty_details() -> None:
    first = client.post("/chat", json={"message": "I need to initialise warranty replacement to my cpu"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "sd20,6445,2025-04-05",
        },
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert "warranty replacement initialized." in body["response"].lower()


def test_chat_prompts_for_purchase_date_when_model_and_serial_have_no_comma() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "sd20 6445",
        },
    )
    second_body = second.json()

    assert second.status_code == 200
    assert second_body["route"] == "customer_support"
    assert second_body["intent"] == "warranty_claim"
    assert "please enter the purchase date" in second_body["response"].lower()

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "2026-01-15",
        },
    )
    third_body = third.json()

    assert third.status_code == 200
    assert third_body["route"] == "customer_support"
    assert third_body["intent"] == "warranty_claim"
    assert "warranty replacement initialized." in third_body["response"].lower()


def test_chat_parses_freeform_product_name_and_serial() -> None:
    first = client.post("/chat", json={"message": "I want to claim warranty for my camera"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "Atlas CX100 Mirrorless Camera 8656",
        },
    )
    second_body = second.json()

    assert second.status_code == 200
    assert second_body["route"] == "customer_support"
    assert second_body["intent"] == "warranty_claim"
    assert "please enter the purchase date" in second_body["response"].lower()

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "2026-01-15",
        },
    )
    third_body = third.json()

    assert third.status_code == 200
    assert third_body["route"] == "customer_support"
    assert third_body["intent"] == "warranty_claim"
    assert "warranty replacement initialized." in third_body["response"].lower()


def test_chat_answers_follow_up_after_user_shares_tried_steps() -> None:
    first = client.post("/chat", json={"message": "My router keeps disconnecting"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "I already restarted it and moved it away from the wall",
        },
    )
    body = second.json()

    assert second.status_code == 200
    assert body["route"] == "tech_support"
    assert body["intent"] == "router_disconnect_issue"
    assert "since you've already tried restarting the router" in body["response"].lower()
    assert "next try" in body["response"].lower()


def test_chat_keeps_router_context_for_ambiguous_overheating_follow_up() -> None:
    first = client.post("/chat", json={"message": "My router keeps disconnecting"}).json()
    conversation_id = first["conversation_id"]

    second = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "I already restarted it and moved it away from the wall",
        },
    ).json()
    assert second["route"] == "tech_support"
    assert "restarted" in second["response"].lower()
    assert "next" in second["response"].lower()

    third = client.post(
        "/chat",
        json={
            "conversation_id": conversation_id,
            "message": "it is overheating now",
        },
    )
    body = third.json()

    assert third.status_code == 200
    assert body["route"] == "tech_support"
    assert "router" in body["response"].lower()
    assert "camera" not in body["response"].lower()


def test_chat_logs_agent_context_contents(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.api.routes")

    response = client.post("/chat", json={"message": "place order for AeroLink AX5400 Router"})
    assert response.status_code == 200

    completed = [
        record
        for record in caplog.records
        if getattr(record, "event", "") == "chat_request_completed"
    ]
    assert completed

    payload = completed[-1].__dict__.get("agent_context")
    assert isinstance(payload, dict)
    assert isinstance(payload.get("metadata"), dict)
    assert isinstance(payload.get("shared_memory"), dict)
    assert isinstance(payload["shared_memory"].get("sales_support"), dict)


def test_chat_logs_payload_user_identifier_on_login_attempt(caplog) -> None:
    caplog.set_level(logging.INFO, logger="app.api.routes")

    response = client.post("/chat", json={"user_id": "user_login_001", "message": "hello"})
    assert response.status_code == 200

    received = [
        record
        for record in caplog.records
        if getattr(record, "event", "") == "chat_request_received"
    ]
    assert received

    latest = received[-1]
    assert latest.__dict__.get("login_attempt") is True
    assert latest.__dict__.get("payload_user_identifier") == "user_login_001"


def test_delete_conversation_removes_state() -> None:
    store = InMemoryConversationStore()
    kb = KnowledgeBaseService(Path("data/wiki.txt"))
    workflow = build_support_workflow(NodeDependencies(knowledge_base=kb, tools=build_default_tool_registry()))
    dev_settings = Settings(
        project_root=Path("."),
        app_env="development",
        log_level="info",
        wiki_file_path=Path("data/wiki.txt"),
        enable_debug_endpoints=True,
        model_provider="none",
        azure_openai_base_url="",
        azure_openai_api_key="",
        azure_openai_model="gpt-4.1-mini",
        azure_openai_deployment="",
        llm_timeout_seconds=20.0,
    )
    dev_app = FastAPI()
    dev_app.include_router(
        create_api_router(
            settings=dev_settings,
            store=store,
            workflow=workflow,
            response_generator=NoopResponseGenerator(),
        )
    )
    dev_client = TestClient(dev_app)

    chat = dev_client.post("/chat", json={"message": "My router keeps disconnecting"}).json()
    conversation_id = chat["conversation_id"]

    debug_before = dev_client.get(f"/debug/conversations/{conversation_id}")
    assert debug_before.status_code == 200

    deleted = dev_client.delete(f"/conversations/{conversation_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}

    debug_after = dev_client.get(f"/debug/conversations/{conversation_id}")
    assert debug_after.status_code == 404


def test_chat_handles_mixed_request_customer_first_then_technical() -> None:
    response = client.post(
        "/chat",
        json={
            "message": "I want to claim warranty for my camera and my router keeps disconnecting",
        },
    )
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert body["response"].startswith("Customer Support Agent:")
    assert "Technical Support Agent:" in body["response"]
    assert body["metadata"]["handoff_target"] == "both_agents"
    assert "router" in body["response"].lower()
    assert "Please choose what to do first" not in body["response"]


def test_warranty_for_wifi_stays_customer_support_only() -> None:
    response = client.post("/chat", json={"message": "how much warranty left for my wifi?"})
    body = response.json()

    assert response.status_code == 200
    assert body["route"] == "customer_support"
    assert body["intent"] == "warranty_claim"
    assert body["metadata"]["handoff_target"] == "customer_support_agent"
    assert body["response"].startswith("Customer Support Agent:")
    assert "Technical Support Agent:" not in body["response"]


def test_invalid_request_handling() -> None:
    response = client.post("/chat", json={"user_id": "u1"})
    assert response.status_code == 400
    assert response.json() == {"error": "message is required"}


def test_debug_endpoint_disabled_in_production() -> None:
    store = InMemoryConversationStore()
    kb = KnowledgeBaseService(Path("data/wiki.txt"))
    workflow = build_support_workflow(NodeDependencies(knowledge_base=kb, tools=build_default_tool_registry()))

    prod_settings = Settings(
        project_root=Path("."),
        app_env="production",
        log_level="info",
        wiki_file_path=Path("data/wiki.txt"),
        enable_debug_endpoints=False,
        model_provider="none",
        azure_openai_base_url="",
        azure_openai_api_key="",
        azure_openai_model="gpt-4.1-mini",
        azure_openai_deployment="",
        llm_timeout_seconds=20.0,
    )
    prod_app = FastAPI()
    prod_app.include_router(
        create_api_router(
            settings=prod_settings,
            store=store,
            workflow=workflow,
            response_generator=NoopResponseGenerator(),
        )
    )
    prod_client = TestClient(prod_app)

    response = prod_client.get("/debug/conversations/conv_123")
    assert response.status_code == 404
