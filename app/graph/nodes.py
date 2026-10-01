from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from app.agents.customer_support import handle_customer_support
from app.agents.fallback import handle_fallback
from app.agents.sales_support import handle_sales_support
from app.agents.tech_support import handle_tech_support
from app.graph.router import decide_route
from app.graph.state import SupportState
from app.services.customer_hint_classifier import (
    CustomerHintClassifier,
    NoopCustomerHintClassifier,
)
from app.services.intent_classifier import IntentClassifier, NoopIntentClassifier
from app.services.knowledge_base import KnowledgeBaseService
from app.services.sales_hint_classifier import NoopSalesHintClassifier, SalesHintClassifier
from app.services.tech_hint_classifier import NoopTechHintClassifier, TechHintClassifier
from app.services.tool_registry import ToolRegistry


@dataclass(frozen=True)
class NodeDependencies:
    knowledge_base: KnowledgeBaseService
    tools: ToolRegistry
    intent_classifier: IntentClassifier = field(default_factory=NoopIntentClassifier)
    customer_hint_classifier: CustomerHintClassifier = field(default_factory=NoopCustomerHintClassifier)
    tech_hint_classifier: TechHintClassifier = field(default_factory=NoopTechHintClassifier)
    sales_hint_classifier: SalesHintClassifier = field(default_factory=NoopSalesHintClassifier)


def greeting_node(state: SupportState) -> dict:
    if state.get("greeted"):
        return {}
    return {"greeted": True}


def router_node(state: SupportState, deps: NodeDependencies | None = None) -> dict:
    latest_message = state.get("latest_user_message", "")
    classifier = deps.intent_classifier if deps is not None else NoopIntentClassifier()
    decision = decide_route(
        latest_message,
        state=state,
        intent_classifier=classifier,
    )

    metadata = dict(state.get("metadata", {}))
    metadata["mixed_support_request"] = bool(decision.mixed_support_request)
    return {
        "route": decision.route,
        "intent": decision.intent,
        "confidence": decision.confidence,
        "metadata": metadata,
    }


def route_from_state(
    state: SupportState,
) -> Literal["customer_support_agent", "tech_support_agent", "sales_support_agent", "fallback_node"]:
    route = state.get("route")
    if route == "customer_support":
        return "customer_support_agent"
    if route == "tech_support":
        return "tech_support_agent"
    if route == "sales_support":
        return "sales_support_agent"
    return "fallback_node"


def customer_support_agent_node(state: SupportState, deps: NodeDependencies) -> dict:
    customer_result = handle_customer_support(state, deps.tools, deps.customer_hint_classifier)
    metadata = state.get("metadata", {})
    has_mixed_request = isinstance(metadata, dict) and bool(metadata.get("mixed_support_request"))
    if not has_mixed_request:
        return customer_result

    latest_message = state.get("latest_user_message", "")
    tech_result = handle_tech_support(
        {
            "latest_user_message": latest_message,
            "metadata": {},
        },
        deps.knowledge_base,
        deps.tech_hint_classifier,
    )
    customer_meta = dict(customer_result.get("metadata", {}))
    tech_meta = dict(tech_result.get("metadata", {}))

    merged_items: list[dict] = []
    customer_hint = customer_meta.get("llm_hints")
    if isinstance(customer_hint, dict):
        merged_items.append(customer_hint)
    tech_hint = tech_meta.get("llm_hints")
    if isinstance(tech_hint, dict):
        merged_items.append(tech_hint)

    customer_meta["mixed_support_request"] = True
    customer_meta["llm_hints"] = {
        "agent": "mixed_support",
        "status": "customer_and_tech",
        "items": merged_items,
    }
    customer_result["metadata"] = customer_meta
    customer_result["response"] = ""
    return customer_result


def tech_support_agent_node(state: SupportState, deps: NodeDependencies) -> dict:
    return handle_tech_support(state, deps.knowledge_base, deps.tech_hint_classifier)


def sales_support_agent_node(state: SupportState, deps: NodeDependencies) -> dict:
    return handle_sales_support(state, deps.tools, deps.sales_hint_classifier)


def fallback_node(state: SupportState) -> dict:
    return handle_fallback(state)
