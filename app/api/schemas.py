from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.graph.state import RouteType


class ChatRequest(BaseModel):
    conversation_id: str | None = None
    user_id: str | None = None
    message: str | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    route: RouteType
    intent: str
    response: str
    tool_calls: list[dict[str, Any]]
    metadata: dict[str, Any]


class DebugConversationResponse(BaseModel):
    conversation_id: str
    state: dict[str, Any]

