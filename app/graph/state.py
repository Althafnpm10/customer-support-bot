from __future__ import annotations

from typing import Any, Literal, TypedDict


RouteType = Literal["customer_support", "tech_support", "sales_support", "fallback"]


class SupportState(TypedDict):
    conversation_id: str
    user_id: str | None
    messages: list[dict[str, str]]
    latest_user_message: str
    greeted: bool
    route: RouteType
    intent: str
    confidence: float
    response: str
    tool_calls: list[dict[str, Any]]
    metadata: dict[str, Any]
    extracted_entities: dict[str, Any]
    shared_memory: dict[str, Any]
