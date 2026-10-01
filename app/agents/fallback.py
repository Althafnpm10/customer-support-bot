from __future__ import annotations

from typing import Any

from app.services.product_scope import find_unsupported_item


def handle_fallback(state: dict[str, Any]) -> dict[str, Any]:
    metadata = dict(state.get("metadata", {}))
    latest_message = str(state.get("latest_user_message", ""))
    intent = str(state.get("intent") or "unknown")
    unsupported_item = find_unsupported_item(latest_message)

    llm_hints: dict[str, Any] = {
        "agent": "fallback",
        "intent": intent,
        "latest_user_message": latest_message,
    }
    if unsupported_item:
        llm_hints["status"] = "unsupported_item"
        llm_hints["unsupported_item"] = unsupported_item
    else:
        llm_hints["status"] = intent or "unknown"

    metadata["llm_hints"] = llm_hints
    return {"response": "", "metadata": metadata}
