from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping, Protocol

import httpx

_ALLOWED_SECTIONS: set[str] = {"general", "router", "camera", "wifi_modem", "cpu"}
_ALLOWED_STEP_IDS: set[str] = {"restart", "reset", "cable", "firmware", "overheat", "placement", "battery"}


@dataclass(frozen=True)
class TechHintDecision:
    section: str = "general"
    follow_up_attempt: bool = False
    attempted_step_ids: list[str] | None = None
    non_resolvable_issue: bool = False
    confidence: float = 0.0


class TechHintClassifier(Protocol):
    def classify(
        self,
        *,
        latest_user_message: str,
        state: Mapping[str, Any] | None = None,
    ) -> TechHintDecision:
        ...


@dataclass(frozen=True)
class NoopTechHintClassifier:
    def classify(
        self,
        *,
        latest_user_message: str,
        state: Mapping[str, Any] | None = None,
    ) -> TechHintDecision:
        return TechHintDecision(section="general", attempted_step_ids=[])


@dataclass(frozen=True)
class AzureOpenAITechHintClassifier:
    base_url: str
    api_key: str
    model: str
    deployment: str = ""
    timeout_seconds: float = 20.0

    def classify(
        self,
        *,
        latest_user_message: str,
        state: Mapping[str, Any] | None = None,
    ) -> TechHintDecision:
        context = _classification_payload(
            latest_user_message=latest_user_message,
            state=dict(state) if isinstance(state, Mapping) else {},
        )
        try:
            model_output = self._generate_classification(context=context)
        except Exception:
            return NoopTechHintClassifier().classify(latest_user_message=latest_user_message, state=state)
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


def _classification_payload(*, latest_user_message: str, state: dict[str, Any]) -> dict[str, Any]:
    history = state.get("messages", [])
    if not isinstance(history, list):
        history = []
    metadata = state.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    return {
        "latest_user_message": latest_user_message,
        "previous_route": state.get("route") or "fallback",
        "previous_intent": state.get("intent") or "unknown",
        "awaiting_tech_attempts": bool(metadata.get("awaiting_tech_attempts")),
        "last_tech_section": metadata.get("last_tech_section"),
        "recent_messages": history[-8:],
        "metadata": metadata,
        "shared_memory": state.get("shared_memory", {}),
    }


def _sanitize_decision(raw: dict[str, Any]) -> TechHintDecision:
    section_candidate = str(raw.get("section") or "general").strip().lower()
    section = section_candidate if section_candidate in _ALLOWED_SECTIONS else "general"

    attempted_raw = raw.get("attempted_step_ids", [])
    attempted_ids: list[str] = []
    if isinstance(attempted_raw, list):
        for item in attempted_raw:
            value = str(item).strip().lower()
            if value in _ALLOWED_STEP_IDS and value not in attempted_ids:
                attempted_ids.append(value)

    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return TechHintDecision(
        section=section,
        follow_up_attempt=bool(raw.get("follow_up_attempt", False)),
        attempted_step_ids=attempted_ids,
        non_resolvable_issue=bool(raw.get("non_resolvable_issue", False)),
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
    "You are a technical-support hint classifier for CU Electronics. "
    "Return strict JSON only with this schema: "
    "{\"section\":\"general\",\"follow_up_attempt\":false,\"attempted_step_ids\":[],"
    "\"non_resolvable_issue\":false,\"confidence\":0.0}. "
    "Allowed section values: general, router, camera, wifi_modem, cpu. "
    "Allowed attempted_step_ids: restart, reset, cable, firmware, overheat, placement, battery. "
    "Set follow_up_attempt=true only when the latest message is a follow-up describing what troubleshooting was already tried. "
    "Set non_resolvable_issue=true only when the user indicates the issue cannot be repaired/resolved or device is irreparably damaged. "
    "Use prior conversation context and metadata. Set confidence between 0 and 1."
)
