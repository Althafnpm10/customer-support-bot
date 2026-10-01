from __future__ import annotations

from app.services.sales_hint_classifier import NoopSalesHintClassifier


def test_noop_classifier_maps_order_placement_intent() -> None:
    decision = NoopSalesHintClassifier().classify(
        latest_user_message="place order for AeroLink AX5400 Router",
        intent="order_placement",
    )

    assert decision.action == "order_placement"
    assert decision.switch_to_other_support is False


def test_noop_classifier_extracts_order_reference() -> None:
    decision = NoopSalesHintClassifier().classify(
        latest_user_message="please cancel MOCK-ORDER-ABC123",
        intent="sales_general",
    )

    assert decision.order_reference == "MOCK-ORDER-ABC123"


def test_noop_classifier_extracts_comma_delimited_address() -> None:
    decision = NoopSalesHintClassifier().classify(
        latest_user_message="45 Market Street, San Francisco, CA 94105",
        intent="order_placement",
    )

    assert decision.shipping_address == {
        "street": "45 Market Street",
        "city": "San Francisco",
        "state": "CA",
        "pin": "94105",
    }


def test_noop_classifier_extracts_uk_style_address() -> None:
    decision = NoopSalesHintClassifier().classify(
        latest_user_message="221B Baker Street London Greater London NW1 6XE UK",
        intent="order_placement",
    )

    assert decision.shipping_address == {
        "street": "221B Baker Street",
        "city": "London",
        "state": "Greater London",
        "pin": "NW1 6XE",
    }
