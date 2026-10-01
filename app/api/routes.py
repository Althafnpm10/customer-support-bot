from __future__ import annotations

import logging
from copy import deepcopy
from time import perf_counter
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from app.api.schemas import ChatRequest, ChatResponse, DebugConversationResponse
from app.config import Settings
from app.services.response_generator import ResponseGenerator
from app.storage.conversation_store import InMemoryConversationStore

logger = logging.getLogger(__name__)


def create_api_router(
    *,
    settings: Settings,
    store: InMemoryConversationStore,
    workflow: object,
    response_generator: ResponseGenerator,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @router.post("/chat", response_model=ChatResponse)
    def chat(payload: ChatRequest) -> ChatResponse | JSONResponse:
        started_at = perf_counter()
        payload_user_id = (payload.user_id or "").strip()
        payload_conversation_id = (payload.conversation_id or "").strip()
        is_login_attempt = not bool(payload_conversation_id)
        message = (payload.message or "").strip()
        if not message:
            logger.info(
                "chat_request_rejected",
                extra={
                    "event": "chat_request_rejected",
                    "reason": "message_required",
                    "conversation_id_provided": bool(payload_conversation_id),
                    "user_id_provided": bool(payload_user_id),
                    "login_attempt": is_login_attempt,
                    "payload_user_identifier": payload_user_id or None,
                },
            )
            return JSONResponse(status_code=400, content={"error": "message_required"})

        conversation_id = payload_conversation_id or _new_conversation_id()
        state = store.get_or_create(conversation_id=conversation_id, user_id=payload.user_id)

        if payload.user_id and not state.get("user_id"):
            state["user_id"] = payload.user_id

        logger.info(
            "chat_request_received",
            extra={
                "event": "chat_request_received",
                "conversation_id": conversation_id,
                "message_length": len(message),
                "message_count_before": len(state.get("messages", [])),
                "user_id_provided": bool(payload_user_id),
                "login_attempt": is_login_attempt,
                "payload_user_identifier": payload_user_id or None,
                "agent_context_before": _agent_context_contents(state),
            },
        )

        state["latest_user_message"] = message
        state["messages"] = [*state.get("messages", []), {"role": "user", "content": message}]

        try:
            result = workflow.invoke(deepcopy(state))
        except Exception:
            logger.exception(
                "chat_request_failed",
                extra={
                    "event": "chat_request_failed",
                    "conversation_id": conversation_id,
                    "duration_ms": int((perf_counter() - started_at) * 1000),
                },
            )
            raise

        result.setdefault("shared_memory", state.get("shared_memory", {}))
        route = result.get("route", "fallback")
        intent = result.get("intent") or "unknown"
        try:
            response_text = response_generator.generate_response(
                latest_user_message=message,
                route=route,
                intent=intent,
                workflow_result=result,
            )
        except Exception:
            logger.exception(
                "chat_response_generation_failed",
                extra={
                    "event": "chat_response_generation_failed",
                    "conversation_id": conversation_id,
                    "route": route,
                },
            )
            return JSONResponse(
                status_code=503,
                content={"error": "llm_response_generation_failed"},
            )

        if not response_text:
            logger.error(
                "chat_response_generation_empty",
                extra={
                    "event": "chat_response_generation_empty",
                    "conversation_id": conversation_id,
                    "route": route,
                },
            )
            return JSONResponse(
                status_code=503,
                content={"error": "llm_response_generation_empty"},
            )

        result["response"] = response_text
        result["messages"] = [*state["messages"], {"role": "assistant", "content": response_text}]
        store.save(conversation_id=conversation_id, state=result)
        handoff_target = _handoff_target_for(route=route, metadata=result.get("metadata"))
        tool_calls = result.get("tool_calls", [])

        logger.info(
            "chat_request_completed",
            extra={
                "event": "chat_request_completed",
                "conversation_id": conversation_id,
                "route": route,
                "intent": intent,
                "handoff_target": handoff_target,
                "tool_call_count": len(tool_calls),
                "duration_ms": int((perf_counter() - started_at) * 1000),
                "agent_context": _agent_context_contents(result),
            },
        )

        return ChatResponse(
            conversation_id=conversation_id,
            route=route,
            intent=intent,
            response=response_text,
            tool_calls=tool_calls,
            metadata={
                "greeted": bool(result.get("greeted", False)),
                "handoff_target": handoff_target,
            },
        )

    @router.delete("/conversations/{conversation_id}")
    def delete_conversation(conversation_id: str) -> dict[str, bool]:
        deleted = store.delete(conversation_id)
        logger.info(
            "conversation_delete_requested",
            extra={
                "event": "conversation_delete_requested",
                "conversation_id": conversation_id,
                "deleted": deleted,
            },
        )
        return {"deleted": deleted}

    @router.get(
        "/debug/conversations/{conversation_id}",
        response_model=DebugConversationResponse,
    )
    def debug_conversation(conversation_id: str) -> DebugConversationResponse:
        if not settings.enable_debug_endpoints:
            raise HTTPException(status_code=404, detail="Not Found")

        state = store.get(conversation_id)
        if state is None:
            raise HTTPException(status_code=404, detail="Conversation not found")

        return DebugConversationResponse(conversation_id=conversation_id, state=state)

    return router


def _new_conversation_id() -> str:
    return f"conv_{uuid4().hex[:8]}"


def _handoff_target_for(*, route: str, metadata: object) -> str:
    if route == "customer_support":
        if isinstance(metadata, dict) and bool(metadata.get("mixed_support_request")):
            return "both_agents"
        return "customer_support_agent"
    if route == "tech_support":
        return "technical_support_agent"
    if route == "sales_support":
        return "sales_support_agent"
    return "support_triage_agent"


def _agent_context_contents(state: dict[str, object]) -> dict[str, object]:
    metadata = state.get("metadata")
    extracted_entities = state.get("extracted_entities")
    shared_memory = state.get("shared_memory")

    context: dict[str, object] = {}
    if isinstance(metadata, dict) and metadata:
        context["metadata"] = deepcopy(metadata)
    if isinstance(extracted_entities, dict) and extracted_entities:
        context["extracted_entities"] = deepcopy(extracted_entities)
    if isinstance(shared_memory, dict) and shared_memory:
        context["shared_memory"] = deepcopy(shared_memory)
    return context
