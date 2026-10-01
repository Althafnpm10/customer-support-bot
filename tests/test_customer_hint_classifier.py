from __future__ import annotations

from app.services.customer_hint_classifier import NoopCustomerHintClassifier


def test_noop_customer_hint_classifier_returns_default_decision() -> None:
    decision = NoopCustomerHintClassifier().classify(
        latest_user_message="do you remember my warranty replacement?",
        intent="warranty_claim",
    )

    assert decision.warranty_memory_lookup is False
    assert decision.warranty_cancellation is False
    assert decision.non_eligible_replacement_case is False
    assert decision.cancel_reason_product_started_working is False
    assert decision.confidence == 0.0
