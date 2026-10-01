#this file routes the incoming customer request   
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from app.graph.state import RouteType
from app.services.intent_classifier import (
    IntentClassifier,
    NoopIntentClassifier,
)


@dataclass(frozen=True)
class RouteDecision:
    route: RouteType
    intent: str
    confidence: float
    mixed_support_request: bool = False


def decide_route(
    message: str,
    *,
    state: Mapping[str, Any] | None = None,
    intent_classifier: IntentClassifier | None = None,
) -> RouteDecision:
    classifier = intent_classifier or NoopIntentClassifier()
    decision = classifier.classify(latest_user_message=message, state=state)
    return RouteDecision(
        route=decision.route,
        intent=decision.intent,
        confidence=decision.confidence,
        mixed_support_request=decision.mixed_support_request,
    )


def has_mixed_support_request(
    message: str,
    *,
    state: Mapping[str, Any] | None = None,
    intent_classifier: IntentClassifier | None = None,
) -> bool:
    decision = decide_route(message, state=state, intent_classifier=intent_classifier)
    return decision.mixed_support_request
