from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx


@dataclass(frozen=True)
class CustomerHintDecision:
    warranty_memory_lookup: bool = False
    warranty_cancellation: bool = False
    non_eligible_replacement_case: bool = False
    cancel_reason_product_started_working: bool = False
    confidence: float = 0.0


class CustomerHintClassifier(Protocol):
    def classify(
        self,
        *,
        latest_user_message: str,
        intent: str,
        state: Mapping[str, Any] | None = None,
    ) -> CustomerHintDecision:
        ...


@dataclass(frozen=True)
class NoopCustomerHintClassifier:
    def classify(
        self,
        *,
        latest_user_message: str,
        intent: str,
        state: Mapping[str, Any] | None = None,
    ) -> CustomerHintDecision:
        # In non-LLM mode we avoid branch heuristics and fall back to intent-driven flow.
        return CustomerHintDecision()


@dataclass(frozen=True)
class AzureOpenAICustomerHintClassifier:
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
    ) -> CustomerHintDecision:
        context = _classification_payload(
            latest_user_message=latest_user_message,
            intent=intent,
            state=dict(state) if isinstance(state, Mapping) else {},
        )
        try:
            model_output = self._generate_classification(context=context)
        except Exception:
            return NoopCustomerHintClassifier().classify(
                latest_user_message=latest_user_message,
                intent=intent,
                state=state,
            )
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

    shared_memory = state.get("shared_memory", {})
    if not isinstance(shared_memory, dict):
        shared_memory = {}

    customer_memory = shared_memory.get("customer_support", {})
    if not isinstance(customer_memory, dict):
        customer_memory = {}

    return {
        "latest_user_message": latest_user_message,
        "current_intent": intent,
        "previous_route": state.get("route") or "fallback",
        "previous_intent": state.get("intent") or "unknown",
        "active_warranty_replacement": customer_memory.get("active_warranty_replacement"),
        "last_warranty_replacement": customer_memory.get("last_warranty_replacement"),
        "recent_messages": history[-8:],
        "shared_memory": shared_memory,
    }


def _sanitize_decision(raw: dict[str, Any]) -> CustomerHintDecision:
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return CustomerHintDecision(
        warranty_memory_lookup=bool(raw.get("warranty_memory_lookup", False)),
        warranty_cancellation=bool(raw.get("warranty_cancellation", False)),
        non_eligible_replacement_case=bool(raw.get("non_eligible_replacement_case", False)),
        cancel_reason_product_started_working=bool(raw.get("cancel_reason_product_started_working", False)),
        confidence=confidence,
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
    "You are a customer-support hint classifier for CU Electronics. "
    "Return strict JSON only with this schema: "
    "{\"warranty_memory_lookup\":false,\"warranty_cancellation\":false,"
    "\"non_eligible_replacement_case\":false,\"cancel_reason_product_started_working\":false,\"confidence\":0.0}. "
    "Set warranty_memory_lookup=true only when the user is asking to recall previous warranty/replacement details. "
    "Set warranty_cancellation=true only when the user is cancelling an active warranty/replacement request. "
    "Set non_eligible_replacement_case=true only when the message indicates damage/non-eligibility and replacement cannot be issued. "
    "Set cancel_reason_product_started_working=true only when the user says it started working again. "
    "Use intent, recent messages, and memory context. Set confidence between 0 and 1."
)
