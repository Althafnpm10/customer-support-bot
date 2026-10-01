from __future__ import annotations

from copy import deepcopy
from threading import Lock

from app.graph.state import SupportState


def new_state(conversation_id: str, user_id: str | None = None) -> SupportState:
    return {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "messages": [],
        "latest_user_message": "",
        "greeted": False,
        "route": "fallback",
        "intent": "unknown",
        "confidence": 0.0,
        "response": "",
        "tool_calls": [],
        "metadata": {},
        "extracted_entities": {},
        "shared_memory": {},
    }


class InMemoryConversationStore:
    """
    v1 in-memory conversation storage.
    Limitations: reset on server restart, not multi-instance safe, not production-ready.
    """

    def __init__(self) -> None:
        self._store: dict[str, SupportState] = {}
        self._lock = Lock()

    def get(self, conversation_id: str) -> SupportState | None:
        with self._lock:
            state = self._store.get(conversation_id)
            return deepcopy(state) if state is not None else None

    def get_or_create(self, conversation_id: str, user_id: str | None = None) -> SupportState:
        with self._lock:
            existing = self._store.get(conversation_id)
            if existing is None:
                existing = new_state(conversation_id=conversation_id, user_id=user_id)
                self._store[conversation_id] = existing
            state = deepcopy(existing)
            state.setdefault("shared_memory", {})
            if user_id and not state.get("user_id"):
                state["user_id"] = user_id
            return state

    def save(self, conversation_id: str, state: SupportState) -> None:
        with self._lock:
            self._store[conversation_id] = deepcopy(state)

    def delete(self, conversation_id: str) -> bool:
        with self._lock:
            if conversation_id in self._store:
                del self._store[conversation_id]
                return True
            return False
