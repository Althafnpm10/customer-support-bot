from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Protocol

import httpx


class ResponseGenerator(Protocol):
    def generate_response(
        self,
        *,
        latest_user_message: str,
        route: str,
        intent: str,
        workflow_result: dict[str, Any],
    ) -> str:
        ...


@dataclass(frozen=True)
class NoopResponseGenerator:
    """Returns the workflow-produced response without LLM generation."""

    def generate_response(
        self,
        *,
        latest_user_message: str,
        route: str,
        intent: str,
        workflow_result: dict[str, Any],
    ) -> str:
        return ""


@dataclass(frozen=True)
class AzureOpenAIResponseGenerator:
    base_url: str
    api_key: str
    model: str
    deployment: str = ""
    timeout_seconds: float = 20.0

    def generate_response(
        self,
        *,
        latest_user_message: str,
        route: str,
        intent: str,
        workflow_result: dict[str, Any],
    ) -> str:
        context = _llm_context_payload(
            latest_user_message=latest_user_message,
            route=route,
            intent=intent,
            workflow_result=workflow_result,
        )

        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps(context, ensure_ascii=True)},
        ]
        headers = {
            "Content-Type": "application/json",
            # Keep both for compatibility across Azure-hosted OpenAI-compatible endpoints.
            "Authorization": f"Bearer {self.api_key}",
            "api-key": self.api_key,
        }

        with httpx.Client(timeout=self.timeout_seconds) as client:
            if self._prefer_responses_api():
                content = self._generate_with_responses_api(client=client, context=context)
                if content:
                    return content

            url, body = self._build_request(messages=messages)
            response = client.post(
                url,
                headers=headers,
                json=body,
            )

            if response.is_error:
                if self._is_unsupported_operation(response):
                    content = self._generate_with_responses_api(client=client, context=context)
                    if content:
                        return content
                response.raise_for_status()

            payload = response.json()

        content = _extract_chat_completion_text(payload).strip()
        if not content:
            raise ValueError("Azure OpenAI returned empty completion content")
        return content

    def _prefer_responses_api(self) -> bool:
        target = f"{self.model} {self.deployment}".lower()
        return "gpt-5" in target or "codex" in target

    def _is_unsupported_operation(self, response: httpx.Response) -> bool:
        try:
            payload = response.json()
        except Exception:
            return False
        message = str(payload.get("error", {}).get("message", "")).lower()
        return "unsupported" in message

    def _generate_with_responses_api(
        self,
        *,
        client: httpx.Client,
        context: dict[str, Any],
    ) -> str:
        model_name = (self.model or self.deployment).strip()
        if not model_name:
            raise ValueError("Azure OpenAI model/deployment is required")

        body: dict[str, Any] = {
            "model": model_name,
            "instructions": _SYSTEM_PROMPT,
            "input": json.dumps(context, ensure_ascii=True),
            "reasoning": {"effort": "high"},
        }
        response = client.post(
            f"{self.base_url.rstrip('/')}/responses",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
                "api-key": self.api_key,
            },
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
        return _extract_responses_text(payload).strip()

    def _build_request(self, *, messages: list[dict[str, str]]) -> tuple[str, dict[str, Any]]:
        if self.deployment:
            resource_base = self.base_url.rstrip("/")
            if resource_base.endswith("/openai/v1"):
                resource_base = resource_base[: -len("/openai/v1")]
            url = (
                f"{resource_base}/openai/deployments/{self.deployment}"
                "/chat/completions?api-version=2024-10-21"
            )
            return url, {"messages": messages, "temperature": 0.2}

        url = f"{self.base_url.rstrip('/')}/chat/completions"
        return url, {"model": self.model, "messages": messages, "temperature": 0.2}


def _extract_chat_completion_text(payload: dict[str, Any]) -> str:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        # Some OpenAI-compatible variants return segmented content items.
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


def _llm_context_payload(
    *,
    latest_user_message: str,
    route: str,
    intent: str,
    workflow_result: dict[str, Any],
) -> dict[str, Any]:
    metadata = workflow_result.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    llm_hints = metadata.get("llm_hints", {})
    extracted_entities = workflow_result.get("extracted_entities", {})
    if not isinstance(extracted_entities, dict):
        extracted_entities = {}
    if route != "customer_support":
        extracted_entities = {}

    conversation_messages = workflow_result.get("messages", [])
    if not isinstance(conversation_messages, list):
        conversation_messages = []
    if route != "customer_support":
        conversation_messages = []

    return {
        "latest_user_message": latest_user_message,
        "route": route,
        "intent": intent,
        "llm_hints": llm_hints,
        "tool_calls": workflow_result.get("tool_calls", []),
        "metadata": metadata,
        "extracted_entities": extracted_entities,
        "shared_memory": workflow_result.get("shared_memory", {}),
        "conversation_messages": conversation_messages[-10:],
    }


_SYSTEM_PROMPT = (
    "You are a customer-facing support agent for CU Electronics. "
    "Generate the final message for the user from the provided JSON context. "
    "Rules: "
    "1) Keep it concise and helpful. "
    "2) Use plain text only (no markdown). "
    "3) Preserve factual details from tool calls, memory, and entities. "
    "4) Do not invent product data, order ids, dates, or policy details not in context. "
    "5) Keep agent prefix style based on route: "
    "customer_support -> 'Customer Support Agent:', "
    "tech_support -> 'Technical Support Agent:', "
    "sales_support -> 'Sales Support Agent:', "
    "fallback -> 'Support Triage Agent:'. "
    "6) Use llm_hints.status and other llm_hints fields as the primary behavior signal. "
    "7) If llm_hints indicates required details, ask specifically for only missing fields. "
    "8) If llm_hints includes recommendation/comparison/order details, include concrete product names, prices, and reference ids from context. "
    "9) If llm_hints.upsell_context is true or llm_hints.escalate_to_sales is true, do not use a fixed template sentence. "
    "Give a concise, persuasive replacement suggestion tailored to the user's issue and include 1-2 recommended products with names and prices from llm_hints.recommended_products when present."
)
