from __future__ import annotations

from app.services.tech_hint_classifier import NoopTechHintClassifier


def test_noop_tech_hint_classifier_returns_default_decision() -> None:
    decision = NoopTechHintClassifier().classify(
        latest_user_message="I restarted it and checked cables",
    )

    assert decision.section == "general"
    assert decision.follow_up_attempt is False
    assert decision.attempted_step_ids == []
    assert decision.non_resolvable_issue is False
    assert decision.confidence == 0.0
