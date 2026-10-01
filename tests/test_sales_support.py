from __future__ import annotations

from app.agents.sales_support import handle_sales_support
from app.services.mock_actions import build_default_tool_registry


def _state(message: str, *, intent: str = "sales_general") -> dict:
    return {
        "conversation_id": "conv_sales",
        "user_id": "user_sales",
        "latest_user_message": message,
        "intent": intent,
        "metadata": {},
        "tool_calls": [],
        "shared_memory": {},
    }


def test_compares_two_user_specified_products() -> None:
    result = handle_sales_support(
        _state("compare Atlas CX100 Mirrorless Camera vs Atlas Vlog Pro 4K", intent="product_comparison"),
        build_default_tool_registry(),
    )

    assert result["response"].startswith("Sales Support Agent:")
    assert "atlas cx100 mirrorless camera" in result["response"].lower()
    assert "atlas vlog pro 4k" in result["response"].lower()
    assert "recommend" in result["response"].lower()


def test_recommends_product_from_feature_requirements() -> None:
    result = handle_sales_support(
        _state("find a suitable router with mesh coverage under $300", intent="feature_based_recommendation"),
        build_default_tool_registry(),
    )

    assert result["response"].startswith("Sales Support Agent:")
    assert "here is the router with" in result["response"].lower()
    assert "aerolink mesh router kit" in result["response"].lower()
    assert "aerolink ax5400 router" not in result["response"].lower()


def test_upsell_response_for_non_eligible_warranty_case() -> None:
    result = handle_sales_support(
        _state(
            "my camera warranty expired and it is physically damaged so cannot issue replacement",
            intent="warranty_replacement_upsell",
        ),
        build_default_tool_registry(),
    )
    lower = result["response"].lower()

    assert result["response"].startswith("Sales Support Agent:")
    assert ("warranty" in lower) or ("damaged" in lower)
    assert any(term in lower for term in ("buy", "new", "recommend", "upgrade", "replacement option"))
    assert ("atlas cx100 mirrorless camera" in lower) or ("atlas vlog pro 4k" in lower)


def test_order_selection_asks_for_delivery_address() -> None:
    result = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )

    assert result["response"].startswith("Sales Support Agent:")
    assert "street, city, state, and pin" in result["response"].lower()
    assert result["tool_calls"] == []


def test_places_order_and_thanks_user_after_address() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("221B Baker Street, San Francisco, CA 94105", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" in second["response"].lower()
    assert "thank you for choosing us" in second["response"].lower()
    assert second["tool_calls"][-1]["tool_name"] == "place_mock_order"
    assert second["tool_calls"][-1]["status"] == "mock_created"
    assert "delivery address:" in second["response"].lower()
    assert "94105" in second["response"]


def test_places_order_from_previous_recommendation_without_repeating_name() -> None:
    first = handle_sales_support(
        _state("suggest a router for streaming under $250", intent="feature_based_recommendation"),
        build_default_tool_registry(),
    )
    second_state = _state("place order", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second_state["metadata"] = first["metadata"]

    second = handle_sales_support(second_state, build_default_tool_registry())
    assert "street, city, state, and pin" in second["response"].lower()

    third_state = _state("45 Market Street, San Francisco, CA 94105", intent="order_placement")
    third_state["shared_memory"] = second["shared_memory"]
    third = handle_sales_support(third_state, build_default_tool_registry())
    assert "your order is placed" in third["response"].lower()
    assert third["tool_calls"][-1]["tool_name"] == "place_mock_order"


def test_cancels_latest_order_using_shared_memory() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 Market Street, San Francisco, CA 94105", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    third_state = _state("cancel my order", intent="order_cancellation")
    third_state["shared_memory"] = second["shared_memory"]

    third = handle_sales_support(third_state, build_default_tool_registry())
    assert "order cancellation is completed" in third["response"].lower()
    assert third["tool_calls"][-1]["tool_name"] == "cancel_mock_order"
    assert third["tool_calls"][-1]["status"] == "mock_cancelled"
    assert third["shared_memory"]["sales_support"]["orders"][-1]["status"] == "cancelled"


def test_cancels_order_by_reference() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 Market Street, San Francisco, CA 94105", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())
    reference = second["tool_calls"][-1]["reference_id"]
    third_state = _state(f"please cancel order {reference}", intent="order_cancellation")
    third_state["shared_memory"] = second["shared_memory"]

    third = handle_sales_support(third_state, build_default_tool_registry())
    assert "order cancellation is completed" in third["response"].lower()
    assert reference in third["response"]


def test_cancell_this_order_phrase_cancels_recent_order() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 Market Street, San Francisco, CA 94105", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    third_state = _state("i need to cancell this order", intent="order_placement")
    third_state["shared_memory"] = second["shared_memory"]
    third = handle_sales_support(third_state, build_default_tool_registry())

    assert "order cancellation is completed" in third["response"].lower()
    assert third["tool_calls"][-1]["tool_name"] == "cancel_mock_order"


def test_cancels_camera_order_by_model_name_only() -> None:
    first = handle_sales_support(
        _state("place order for Atlas CX100 Mirrorless Camera", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 zsd palakkad kerala 678632", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    third_state = _state("place order for Atlas Vlog Pro 4K", intent="order_placement")
    third_state["shared_memory"] = second["shared_memory"]
    third = handle_sales_support(third_state, build_default_tool_registry())
    fourth_state = _state("12 MG Road Bengaluru Karnataka 560001 India", intent="order_placement")
    fourth_state["shared_memory"] = third["shared_memory"]
    fourth = handle_sales_support(fourth_state, build_default_tool_registry())

    cancel_state = _state("cancel the order of camera model cx100", intent="order_cancellation")
    cancel_state["shared_memory"] = fourth["shared_memory"]
    cancelled = handle_sales_support(cancel_state, build_default_tool_registry())

    assert "order cancellation is completed" in cancelled["response"].lower()
    assert "atlas cx100 mirrorless camera" in cancelled["response"].lower()
    orders = cancelled["shared_memory"]["sales_support"]["orders"]
    cx100_orders = [order for order in orders if order["product_name"] == "Atlas CX100 Mirrorless Camera"]
    vlog_orders = [order for order in orders if order["product_name"] == "Atlas Vlog Pro 4K"]
    assert cx100_orders[-1]["status"] == "cancelled"
    assert vlog_orders[-1]["status"] == "placed"


def test_understands_choose_phrase_after_comparison() -> None:
    first = handle_sales_support(
        _state("compare Atlas CX100 Mirrorless Camera vs Atlas Vlog Pro 4K", intent="product_comparison"),
        build_default_tool_registry(),
    )
    second_state = _state("i choose atlas camera", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "street, city, state, and pin" in second["response"].lower()
    assert "atlas" in second["response"].lower()


def test_understands_prefer_xeno_cpu_phrase_from_comparison_context() -> None:
    first = handle_sales_support(
        _state("compare ZenCore X8 Desktop CPU vs ZenCore X12 Creator CPU", intent="product_comparison"),
        build_default_tool_registry(),
    )
    second_state = _state("i prefer xeno cpu", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "street, city, state, and pin" in second["response"].lower()
    assert "zencore" in second["response"].lower()


def test_understands_choose_wifi_phrase_as_wifi_modem_from_comparison_context() -> None:
    first = handle_sales_support(
        _state("compare WaveNet DOCSIS 3.1 Modem vs WaveNet Fiber Gateway", intent="product_comparison"),
        build_default_tool_registry(),
    )
    second_state = _state("i choose wifi", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "street, city, state, and pin" in second["response"].lower()
    assert "wavenet" in second["response"].lower()


def test_recommends_wifi_modem_for_wifi_or_modem_query() -> None:
    result = handle_sales_support(
        _state("i need a wifi modem with gigabit", intent="feature_based_recommendation"),
        build_default_tool_registry(),
    )

    assert "here is the wifi modem with gigabit" in result["response"].lower()
    assert "wavenet docsis 3.1 modem" in result["response"].lower()
    assert "aerolink" not in result["response"].lower()


def test_parses_address_without_commas_with_state_and_pin() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 Market Street San Francisco CA 94105", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" in second["response"].lower()
    assert "45 Market Street, San Francisco, CA - 94105" in second["response"]
    order = second["shared_memory"]["sales_support"]["orders"][-1]
    assert order["street"] == "45 Market Street"
    assert order["city"] == "San Francisco"
    assert order["state"] == "CA"
    assert order["pin"] == "94105"


def test_asks_again_when_address_is_missing_state_or_pin() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 Market Street, San Francisco", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "street, city, state, and pin" in second["response"].lower()
    assert second["tool_calls"] == []


def test_generic_buy_camera_message_does_not_auto_place_previous_choice() -> None:
    first = handle_sales_support(
        _state("place order for Atlas CX100 Mirrorless Camera", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("i need to buy a camera", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" not in second["response"].lower()
    assert "based on your requirements" in second["response"].lower()
    assert second["tool_calls"] == []


def test_generic_buy_with_features_returns_recommendations_not_auto_order() -> None:
    first = handle_sales_support(
        _state("place order for Atlas CX100 Mirrorless Camera", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("i need to buy a camera with 4k and autofocus under $600", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" not in second["response"].lower()
    assert "here is the camera with" in second["response"].lower()
    assert "atlas vlog pro 4k" in second["response"].lower()
    assert "atlas cx100 mirrorless camera" not in second["response"].lower()


def test_returns_only_cpu_with_8_cores_for_specific_feature_query() -> None:
    result = handle_sales_support(
        _state("i need a cpu with 8 cores", intent="feature_based_recommendation"),
        build_default_tool_registry(),
    )

    assert "here is the cpu with 8 cores" in result["response"].lower()
    assert "zencore x8 desktop cpu" in result["response"].lower()
    assert "zencore x12 creator cpu" not in result["response"].lower()


def test_parses_indian_address_without_commas() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("12 MG Road Bengaluru Karnataka 560001 India", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" in second["response"].lower()
    assert "12 MG Road, Bengaluru, Karnataka - 560001" in second["response"]
    order = second["shared_memory"]["sales_support"]["orders"][-1]
    assert order["street"] == "12 MG Road"
    assert order["city"] == "Bengaluru"
    assert order["state"] == "Karnataka"
    assert order["pin"] == "560001"


def test_accepts_alphabetic_street_name_without_numeric() -> None:
    first = handle_sales_support(
        _state("place order for AeroLink AX5400 Router", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("Green Meadows Bengaluru Karnataka 560001 India", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" in second["response"].lower()
    assert "Green Meadows, Bengaluru, Karnataka - 560001" in second["response"]
    assert "street:" not in second["response"].lower()


def test_parses_mixed_numeric_alphabetic_street_without_commas() -> None:
    first = handle_sales_support(
        _state("place order for Atlas CX100 Mirrorless Camera", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("45 zsd palakkad kerala 678632", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" in second["response"].lower()
    assert "45 zsd, Palakkad, Kerala - 678632" in second["response"]
    assert "street:" not in second["response"].lower()
    order = second["shared_memory"]["sales_support"]["orders"][-1]
    assert order["street"] == "45 zsd"
    assert order["city"] == "Palakkad"
    assert order["state"] == "Kerala"
    assert order["pin"] == "678632"


def test_parses_uk_address_without_commas() -> None:
    first = handle_sales_support(
        _state("place order for Atlas CX100 Mirrorless Camera", intent="order_placement"),
        build_default_tool_registry(),
    )
    second_state = _state("221B Baker Street London Greater London NW1 6XE UK", intent="order_placement")
    second_state["shared_memory"] = first["shared_memory"]
    second = handle_sales_support(second_state, build_default_tool_registry())

    assert "your order is placed" in second["response"].lower()
    assert "221B Baker Street, London, Greater London - NW1 6XE" in second["response"]
