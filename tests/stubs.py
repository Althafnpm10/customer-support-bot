from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.intent_classifier import IntentDecision


class DeterministicIntentClassifier:
    """Test-only classifier stub for deterministic routing assertions."""

    def classify(self, *, latest_user_message: str, state: Mapping[str, Any] | None = None) -> IntentDecision:
        text = self._normalize(latest_user_message)
        state = state or {}

        previous_route = str(state.get("route") or "")
        previous_intent = str(state.get("intent") or "")
        if previous_route == "customer_support" and previous_intent in {
            "warranty_claim",
            "replacement_request",
            "service_request",
        }:
            if self._looks_like_serial_only(latest_user_message):
                return IntentDecision(route="customer_support", intent="warranty_claim", confidence=0.82)
            if any(term in text for term in ("model", "serial", "purchase")):
                return IntentDecision(route="customer_support", intent="warranty_claim", confidence=0.82)

        if "warranty" in text and "router" in text and "disconnect" in text:
            return IntentDecision(
                route="customer_support",
                intent="warranty_claim",
                confidence=0.9,
                mixed_support_request=True,
            )

        if any(term in text for term in ("phone", "laptop")):
            return IntentDecision(route="fallback", intent="unsupported_item", confidence=0.95)

        if text in {"hello", "hi", "hey", "good morning", "good afternoon", "good evening"}:
            return IntentDecision(route="fallback", intent="greeting", confidence=0.95)

        if "router" in text and any(term in text for term in ("disconnect", "disconnecting", "drops")):
            return IntentDecision(route="tech_support", intent="router_disconnect_issue", confidence=0.9)
        if "modem" in text and "sync" in text:
            return IntentDecision(route="tech_support", intent="modem_sync_issue", confidence=0.9)

        if "warranty expired" in text or "out of warranty" in text:
            return IntentDecision(route="sales_support", intent="warranty_replacement_upsell", confidence=0.88)

        if "cancel" in text and any(term in text for term in ("warranty", "replacement", "claim", "request")):
            return IntentDecision(route="customer_support", intent="cancel_request", confidence=0.88)
        if "replacement" in text and "warranty" not in text:
            return IntentDecision(route="customer_support", intent="replacement_request", confidence=0.85)
        if "warranty" in text:
            return IntentDecision(route="customer_support", intent="warranty_claim", confidence=0.88)

        if any(term in text for term in ("cancel my order", "cancel order", "cancell this order")):
            return IntentDecision(route="sales_support", intent="order_cancellation", confidence=0.9)
        if any(term in text for term in ("compare", " vs ", " versus ", "difference")):
            return IntentDecision(route="sales_support", intent="product_comparison", confidence=0.9)
        if "i choose" in text or "i pick" in text or "i prefer" in text:
            return IntentDecision(route="sales_support", intent="order_placement", confidence=0.88)
        if "buy" in text or "order" in text or ("purchase" in text and "purchase date" not in text):
            return IntentDecision(route="sales_support", intent="order_placement", confidence=0.88)
        if "need a" in text or "suggest" in text or "recommend" in text:
            return IntentDecision(
                route="sales_support",
                intent="feature_based_recommendation",
                confidence=0.86,
            )

        return IntentDecision(route="fallback", intent="unknown", confidence=0.2)

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(re.findall(r"[a-z0-9\-']+", text.lower()))

    @staticmethod
    def _looks_like_serial_only(message: str) -> bool:
        value = message.strip()
        return bool(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9\-_\/]*", value))
