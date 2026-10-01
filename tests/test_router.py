from __future__ import annotations

from types import SimpleNamespace

from app.graph.nodes import router_node
from app.graph.router import decide_route
from tests.stubs import DeterministicIntentClassifier


_CLASSIFIER = DeterministicIntentClassifier()


def _decide(message: str, *, state: dict | None = None):
    return decide_route(message, state=state, intent_classifier=_CLASSIFIER)


def _route_node(state: dict):
    deps = SimpleNamespace(intent_classifier=_CLASSIFIER)
    return router_node(state, deps)


def test_routes_to_customer_support_for_warranty() -> None:
    decision = _decide("I want to claim warranty")
    assert decision.route == "customer_support"
    assert decision.intent == "warranty_claim"


def test_routes_to_customer_support_for_warranty_with_product_context() -> None:
    decision = _decide("I want to claim warranty for my camera")
    assert decision.route == "customer_support"
    assert decision.intent == "warranty_claim"


def test_routes_to_tech_support_for_router_disconnect() -> None:
    decision = _decide("My router disconnects every hour")
    assert decision.route == "tech_support"
    assert decision.intent == "router_disconnect_issue"


def test_routes_to_tech_support_for_modem_sync_issue() -> None:
    decision = _decide("My wifi modem loses sync frequently")
    assert decision.route == "tech_support"
    assert decision.intent == "modem_sync_issue"


def test_routes_phone_battery_to_main_agent_as_unsupported() -> None:
    decision = _decide("My phone battery drains fast")
    assert decision.route == "fallback"
    assert decision.intent == "unsupported_item"


def test_routes_to_customer_support_for_replacement() -> None:
    decision = _decide("I need a replacement")
    assert decision.route == "customer_support"
    assert decision.intent == "replacement_request"


def test_routes_to_customer_support_for_warranty_cancellation() -> None:
    decision = _decide("Please cancel my warranty replacement request")
    assert decision.route == "customer_support"
    assert decision.intent == "cancel_request"


def test_routes_warranty_replacement_phrase_to_warranty_claim() -> None:
    decision = _decide("I need warranty replacement for my camera")
    assert decision.route == "customer_support"
    assert decision.intent == "warranty_claim"


def test_routes_issue_warranty_phrase_to_warranty_claim() -> None:
    decision = _decide("issue warranty for my camera")
    assert decision.route == "customer_support"
    assert decision.intent == "warranty_claim"


def test_routes_access_warranty_phrase_to_warranty_claim() -> None:
    decision = _decide("I want to access warranty")
    assert decision.route == "customer_support"
    assert decision.intent == "warranty_claim"


def test_routes_to_fallback_for_unclear_message() -> None:
    decision = _decide("Hello")
    assert decision.route == "fallback"
    assert decision.intent == "greeting"


def test_routes_laptop_to_main_agent_as_unsupported() -> None:
    decision = _decide("My laptop fan is too loud")
    assert decision.route == "fallback"
    assert decision.intent == "unsupported_item"


def test_routes_mixed_customer_and_technical_to_customer_support() -> None:
    decision = _decide("I want to claim warranty for my camera and my router keeps disconnecting")
    assert decision.route == "customer_support"
    assert decision.intent == "warranty_claim"


def test_routes_purchase_question_to_sales_support() -> None:
    decision = _decide("Can I buy a CPU from this website?")
    assert decision.route == "sales_support"
    assert decision.intent == "order_placement"


def test_routes_compare_request_to_sales_support() -> None:
    decision = _decide("Compare Atlas CX100 Mirrorless Camera vs Atlas Vlog Pro 4K")
    assert decision.route == "sales_support"
    assert decision.intent == "product_comparison"


def test_routes_feature_based_recommendation_to_sales_support() -> None:
    decision = _decide("Suggest a router for streaming under $250")
    assert decision.route == "sales_support"
    assert decision.intent == "feature_based_recommendation"


def test_routes_need_product_with_feature_to_sales_support() -> None:
    decision = _decide("I need a camera with 4k")
    assert decision.route == "sales_support"
    assert decision.intent == "feature_based_recommendation"


def test_routes_wifi_modem_feature_request_to_sales_support() -> None:
    decision = _decide("I need a wifi modem with gigabit")
    assert decision.route == "sales_support"
    assert decision.intent == "feature_based_recommendation"


def test_routes_warranty_expired_purchase_guidance_to_sales_support() -> None:
    decision = _decide("My warranty expired and the camera is damaged, suggest a new one")
    assert decision.route == "sales_support"
    assert decision.intent == "warranty_replacement_upsell"


def test_routes_order_cancel_to_sales_support() -> None:
    decision = _decide("Please cancel my order")
    assert decision.route == "sales_support"
    assert decision.intent == "order_cancellation"


def test_routes_misspelled_cancell_order_to_sales_support() -> None:
    decision = _decide("I need to cancell this order")
    assert decision.route == "sales_support"
    assert decision.intent == "order_cancellation"


def test_routes_choose_phrase_to_order_placement() -> None:
    decision = _decide("I choose atlas camera")
    assert decision.route == "sales_support"
    assert decision.intent == "order_placement"


def test_customer_follow_up_does_not_override_router_issue_with_active_warranty_context() -> None:
    state = {
        "conversation_id": "conv_1",
        "user_id": "user_1",
        "messages": [],
        "latest_user_message": "My router disconnects every hour and it is getting worse",
        "greeted": True,
        "route": "customer_support",
        "intent": "warranty_claim",
        "confidence": 0.8,
        "response": "",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {"product_type": "camera"},
        "shared_memory": {
            "customer_support": {
                "active_warranty_replacement": {
                    "status": "active",
                    "product_type": "camera",
                    "model": "RX-100",
                    "serial_number": "555001",
                    "purchase_date": "2026-01-15",
                }
            }
        },
    }

    decision = _route_node(state)
    assert decision["route"] == "tech_support"
    assert decision["intent"] == "router_disconnect_issue"


def test_customer_follow_up_warranty_details_not_misrouted_to_sales() -> None:
    state = {
        "conversation_id": "conv_2",
        "user_id": "user_2",
        "messages": [],
        "latest_user_message": "model name: RX-100, serial number: 555001, purchase date: 2020-01-01",
        "greeted": True,
        "route": "customer_support",
        "intent": "warranty_claim",
        "confidence": 0.8,
        "response": "",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {"product_type": "camera"},
        "shared_memory": {},
    }

    decision = _route_node(state)
    assert decision["route"] == "customer_support"
    assert decision["intent"] == "warranty_claim"


def test_customer_follow_up_serial_only_numeric_stays_customer_support() -> None:
    state = {
        "conversation_id": "conv_3",
        "user_id": "user_3",
        "messages": [],
        "latest_user_message": "4545",
        "greeted": True,
        "route": "customer_support",
        "intent": "warranty_claim",
        "confidence": 0.8,
        "response": "",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {"product_type": "camera", "model": "RX-100"},
        "shared_memory": {},
    }

    decision = _route_node(state)
    assert decision["route"] == "customer_support"
    assert decision["intent"] == "warranty_claim"


def test_customer_follow_up_serial_only_alphanumeric_stays_customer_support() -> None:
    state = {
        "conversation_id": "conv_4",
        "user_id": "user_4",
        "messages": [],
        "latest_user_message": "SN-45A",
        "greeted": True,
        "route": "customer_support",
        "intent": "warranty_claim",
        "confidence": 0.8,
        "response": "",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {"product_type": "camera", "model": "RX-100"},
        "shared_memory": {},
    }

    decision = _route_node(state)
    assert decision["route"] == "customer_support"
    assert decision["intent"] == "warranty_claim"
