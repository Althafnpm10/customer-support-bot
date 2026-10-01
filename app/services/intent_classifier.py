from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

from app.graph.state import RouteType

_ROUTES: set[str] = {"customer_support", "tech_support", "sales_support", "fallback"}
_INTENTS_BY_ROUTE: dict[str, set[str]] = {
    "customer_support": {
        "warranty_claim",
        "service_request",
        "replacement_request",
        "cancel_request",
        "return_request",
        "unknown",
    },
    "tech_support": {
        "router_disconnect_issue",
        "router_slow_speed",
        "modem_sync_issue",
        "modem_connectivity_issue",
        "camera_power_issue",
        "camera_wifi_issue",
        "cpu_performance_issue",
        "unknown",
    },
    "sales_support": {
        "order_cancellation",
        "product_comparison",
        "warranty_replacement_upsell",
        "feature_based_recommendation",
        "order_placement",
        "sales_general",
        "unknown",
    },
    "fallback": {"greeting", "unsupported_item", "unknown"},
}
_DEFAULT_INTENT_BY_ROUTE: dict[str, str] = {
    "customer_support": "warranty_claim",
    "tech_support": "unknown",
    "sales_support": "sales_general",
    "fallback": "unknown",
}


@dataclass(frozen=True)
class IntentDecision:
    route: RouteType
    intent: str
    confidence: float
    mixed_support_request: bool = False


class IntentClassifier(Protocol):
    def classify(self, *, latest_user_message: str, state: Mapping[str, Any] | None = None) -> IntentDecision:
        ...


@dataclass(frozen=True)
class NoopIntentClassifier:
    def classify(self, *, latest_user_message: str, state: Mapping[str, Any] | None = None) -> IntentDecision:
        return IntentDecision(route="fallback", intent="unknown", confidence=0.0, mixed_support_request=False)


@dataclass(frozen=True)
class AzureOpenAIIntentClassifier:
    base_url: str
    api_key: str
    model: str
    deployment: str = ""
    timeout_seconds: float = 20.0

    def classify(self, *, latest_user_message: str, state: Mapping[str, Any] | None = None) -> IntentDecision:
        state_payload = dict(state) if isinstance(state, Mapping) else {}
        context = _classification_payload(latest_user_message=latest_user_message, state=state_payload)
        try:
            model_output = self._generate_classification(context=context)
        except Exception:
            return IntentDecision(route="fallback", intent="unknown", confidence=0.0, mixed_support_request=False)
        return _sanitize_decision(model_output)

    def _generate_classification(self, *, context: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
            "api-key": self.api_key,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            if self._prefer_responses_api():
                body = {
                    "model": (self.model or self.deployment).strip(),
                    "instructions": _CLASSIFIER_SYSTEM_PROMPT,
                    "input": json.dumps(context, ensure_ascii=True),
                    "reasoning": {"effort": "high"},
                }
                response = client.post(
                    f"{self.base_url.rstrip('/')}/responses",
                    headers=headers,
                    json=body,
                )
                response.raise_for_status()
                payload = response.json()
                text = _extract_responses_text(payload).strip()
                return _parse_json_object(text)

            messages = [
                {"role": "system", "content": _CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
            ]
            url, body = self._build_chat_completions_request(messages=messages)
            response = client.post(url, headers=headers, json=body)
            response.raise_for_status()
            payload = response.json()
            text = _extract_chat_completion_text(payload).strip()
            return _parse_json_object(text)

    def _prefer_responses_api(self) -> bool:
        target = f"{self.model} {self.deployment}".lower()
        return "gpt-5" in target or "codex" in target

    def _build_chat_completions_request(
        self,
        *,
        messages: list[dict[str, str]],
    ) -> tuple[str, dict[str, Any]]:
        if self.deployment:
            resource_base = self.base_url.rstrip("/")
            if resource_base.endswith("/openai/v1"):
                resource_base = resource_base[: -len("/openai/v1")]
            url = (
                f"{resource_base}/openai/deployments/{self.deployment}"
                "/chat/completions?api-version=2024-10-21"
            )
            return url, {"messages": messages, "temperature": 0}

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        return url, {"model": self.model, "messages": messages, "temperature": 0}


def _classification_payload(*, latest_user_message: str, state: dict[str, Any]) -> dict[str, Any]:
    history = state.get("messages", [])
    if not isinstance(history, list):
        history = []

    metadata = state.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    shared_memory = state.get("shared_memory", {})
    if not isinstance(shared_memory, dict):
        shared_memory = {}

    context: dict[str, Any] = {
        "latest_user_message": latest_user_message,
        "previous_route": state.get("route") or "fallback",
        "previous_intent": state.get("intent") or "unknown",
        "recent_messages": history[-8:],
        "metadata": metadata,
        "shared_memory": shared_memory,
    }
    return context


def _sanitize_decision(raw: dict[str, Any]) -> IntentDecision:
    route_candidate = str(raw.get("route") or "").strip()
    route = route_candidate if route_candidate in _ROUTES else "fallback"

    intent_candidate = str(raw.get("intent") or "").strip()
    if intent_candidate not in _INTENTS_BY_ROUTE[route]:
        intent = _DEFAULT_INTENT_BY_ROUTE[route]
    else:
        intent = intent_candidate

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    mixed_support_request = bool(raw.get("mixed_support_request", False))
    return IntentDecision(
        route=route,  # type: ignore[arg-type]
        intent=intent,
        confidence=confidence,
        mixed_support_request=mixed_support_request,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    if not text:
        return {}
    try:
        payload = json.loads(text)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return {}
    try:
        payload = json.loads(match.group(0))
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        return {}
    return {}


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _extract_responses_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if not isinstance(output, list):
        return str(payload.get("output_text") or "")

    parts: list[str] = []
    for item in output:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        content_items = item.get("content", [])
        if not isinstance(content_items, list):
            continue
        for content in content_items:
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str) and text.strip():
                parts.append(text.strip())
    return "\n".join(parts).strip()


_CLASSIFIER_SYSTEM_PROMPT = (
    "You are the intent router for CU Electronics support. "
    "Classify the user request into exactly one route and one intent. "
    "Always return strict JSON only with this schema: "
    "{\"route\":\"...\",\"intent\":\"...\",\"confidence\":0.0,\"mixed_support_request\":false}. "
    "Allowed route values: customer_support, tech_support, sales_support, fallback. "
    "Allowed intents by route: "
    "customer_support -> warranty_claim, service_request, replacement_request, cancel_request, return_request, unknown; "
    "tech_support -> router_disconnect_issue, router_slow_speed, modem_sync_issue, modem_connectivity_issue, camera_power_issue, camera_wifi_issue, cpu_performance_issue, unknown; "
    "sales_support -> order_cancellation, product_comparison, warranty_replacement_upsell, feature_based_recommendation, order_placement, sales_general, unknown; "
    "fallback -> greeting, unsupported_item, unknown. "
    "Use prior conversation context and shared memory to classify short follow-ups like serial numbers or addresses. "
    "If the message combines customer_support and tech_support concerns, set route=customer_support and mixed_support_request=true. "
    "Set confidence between 0 and 1."
)
