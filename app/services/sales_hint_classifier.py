from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

_ALLOWED_ACTIONS: set[str] = {
    "none",
    "order_placement",
    "order_cancellation",
    "product_comparison",
    "checkout_cancel",
    "provide_shipping_address",
}
_DEFAULT_ACTION = "none"
_ORDER_REFERENCE_PATTERN = re.compile(r"\bMOCK-ORDER-[A-Z0-9]+\b", flags=re.IGNORECASE)
_PIN_PATTERN = re.compile(
    r"\b(\d{6}|\d{5}(?:-\d{4})?|[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class SalesHintDecision:
    action: str
    confidence: float
    shipping_address: dict[str, str] | None = None
    order_reference: str = ""
    switch_to_other_support: bool = False


class SalesHintClassifier(Protocol):
    def classify(
        self,
        *,
        latest_user_message: str,
        intent: str,
        state: Mapping[str, Any] | None = None,
    ) -> SalesHintDecision:
        ...


@dataclass(frozen=True)
class NoopSalesHintClassifier:
    def classify(
        self,
        *,
        latest_user_message: str,
        intent: str,
        state: Mapping[str, Any] | None = None,
    ) -> SalesHintDecision:
        action = _action_from_intent(intent)
        return SalesHintDecision(
            action=action,
            confidence=0.0,
            shipping_address=_parse_address_fallback(latest_user_message),
            order_reference=_extract_order_reference_fallback(latest_user_message),
            switch_to_other_support=False,
        )


@dataclass(frozen=True)
class AzureOpenAISalesHintClassifier:
    base_url: str
    api_key: str
    model: str
    deployment: str = ""
    timeout_seconds: float = 20.0

    def classify(
        self,
        *,
        latest_user_message: str,
        intent: str,
        state: Mapping[str, Any] | None = None,
    ) -> SalesHintDecision:
        context = _classification_payload(
            latest_user_message=latest_user_message,
            intent=intent,
            state=dict(state) if isinstance(state, Mapping) else {},
        )
        try:
            model_output = self._generate_classification(context=context)
        except Exception:
            return NoopSalesHintClassifier().classify(
                latest_user_message=latest_user_message,
                intent=intent,
                state=state,
            )

        fallback = NoopSalesHintClassifier().classify(
            latest_user_message=latest_user_message,
            intent=intent,
            state=state,
        )
        return _sanitize_decision(model_output, fallback=fallback)

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
                response = client.post(f"{self.base_url.rstrip('/')}/responses", headers=headers, json=body)
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


def _classification_payload(*, latest_user_message: str, intent: str, state: dict[str, Any]) -> dict[str, Any]:
    history = state.get("messages", [])
    if not isinstance(history, list):
        history = []

    metadata = state.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    shared_memory = state.get("shared_memory", {})
    if not isinstance(shared_memory, dict):
        shared_memory = {}

    sales_memory = shared_memory.get("sales_support", {})
    if not isinstance(sales_memory, dict):
        sales_memory = {}

    return {
        "latest_user_message": latest_user_message,
        "current_intent": intent,
        "previous_route": state.get("route") or "fallback",
        "previous_intent": state.get("intent") or "unknown",
        "pending_order": sales_memory.get("pending_order"),
        "last_order_reference": sales_memory.get("last_order_reference"),
        "recent_messages": history[-8:],
        "metadata": metadata,
        "shared_memory": shared_memory,
    }


def _sanitize_decision(raw: dict[str, Any], *, fallback: SalesHintDecision) -> SalesHintDecision:
    action_candidate = str(raw.get("action") or "").strip()
    action = action_candidate if action_candidate in _ALLOWED_ACTIONS else fallback.action

    try:
        confidence = float(raw.get("confidence", fallback.confidence))
    except (TypeError, ValueError):
        confidence = fallback.confidence
    confidence = max(0.0, min(1.0, confidence))

    shipping_address = _normalize_shipping_address(raw.get("shipping_address")) or fallback.shipping_address
    order_reference = _normalize_order_reference(str(raw.get("order_reference") or "")) or fallback.order_reference
    switch_to_other_support = bool(raw.get("switch_to_other_support", fallback.switch_to_other_support))

    return SalesHintDecision(
        action=action,
        confidence=confidence,
        shipping_address=shipping_address,
        order_reference=order_reference,
        switch_to_other_support=switch_to_other_support,
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


def _action_from_intent(intent: str) -> str:
    if intent == "order_placement":
        return "order_placement"
    if intent == "order_cancellation":
        return "order_cancellation"
    if intent == "product_comparison":
        return "product_comparison"
    return _DEFAULT_ACTION


def _normalize_order_reference(value: str) -> str:
    if not value:
        return ""
    match = _ORDER_REFERENCE_PATTERN.search(value)
    if not match:
        return ""
    return match.group(0).upper()


def _normalize_shipping_address(value: Any) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None

    street = str(value.get("street") or "").strip()
    city = str(value.get("city") or "").strip()
    state = str(value.get("state") or "").strip()
    pin = str(value.get("pin") or "").strip()
    if not (street and city and state and pin):
        return None
    return {"street": street, "city": city, "state": state, "pin": pin}


def _extract_order_reference_fallback(message: str) -> str:
    return _normalize_order_reference(message)


def _parse_address_fallback(message: str) -> dict[str, str] | None:
    text = str(message or "").strip()
    if not text:
        return None

    pin_match = None
    for match in _PIN_PATTERN.finditer(text):
        pin_match = match
    if pin_match is None:
        return None
    pin = pin_match.group(1).strip()

    comma_parts = [part.strip() for part in text.split(",") if part.strip()]
    if len(comma_parts) >= 3:
        street = comma_parts[0]
        city = comma_parts[1]
        state_and_pin = " ".join(comma_parts[2:])
        state = state_and_pin.replace(pin, "").strip(" -")
        if street and city and state:
            return {"street": street, "city": city, "state": state, "pin": pin}

    before_pin = text[: pin_match.start()].strip(" ,")
    if not before_pin:
        return None
    tokens = [tok for tok in re.split(r"\s+", before_pin) if tok]
    if len(tokens) < 3:
        return None

    if len(tokens) >= 4 and tokens[-2].lower() in {"greater", "new", "north", "south", "west", "east"}:
        street = " ".join(tokens[:-3]).strip()
        city = tokens[-3].strip(" ,")
        state = f"{tokens[-2].strip(' ,')} {tokens[-1].strip(' ,')}".strip()
    else:
        street = " ".join(tokens[:-2]).strip()
        city = tokens[-2].strip(" ,")
        state = tokens[-1].strip(" ,")

    if not street or not city or not state:
        return None
    return {"street": street, "city": city, "state": state, "pin": pin}


_CLASSIFIER_SYSTEM_PROMPT = (
    "You are a sales-action hint classifier for CU Electronics support. "
    "Return strict JSON only with this schema: "
    "{\"action\":\"...\",\"confidence\":0.0,\"shipping_address\":{\"street\":\"...\",\"city\":\"...\",\"state\":\"...\",\"pin\":\"...\"}|null,"
    "\"order_reference\":\"...\",\"switch_to_other_support\":false}. "
    "Allowed action values: none, order_placement, order_cancellation, product_comparison, checkout_cancel, provide_shipping_address. "
    "Set action=provide_shipping_address only when the latest user message contains a complete shipping address. "
    "For shipping_address, include street, city, state, pin only when all are available; otherwise return null. "
    "Extract order_reference only when explicitly present (for example MOCK-ORDER-XXXX). "
    "Set switch_to_other_support=true if the user is clearly requesting technical support or customer service/warranty handling instead of sales. "
    "Use the current_intent, pending_order, shared memory, and recent messages to interpret short follow-ups. "
    "Set confidence between 0 and 1."
)
