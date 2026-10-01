from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graph.nodes import (
    NodeDependencies,
    customer_support_agent_node,
    fallback_node,
    greeting_node,
    route_from_state,
    router_node,
    sales_support_agent_node,
    tech_support_agent_node,
)
from app.graph.state import SupportState


def build_support_workflow(deps: NodeDependencies):
    graph = StateGraph(SupportState)

    graph.add_node("greeting", greeting_node)
    graph.add_node(
        "router",
        lambda state: router_node(state, deps),
    )
    graph.add_node(
        "customer_support_agent",
        lambda state: customer_support_agent_node(state, deps),
    )
    graph.add_node(
        "tech_support_agent",
        lambda state: tech_support_agent_node(state, deps),
    )
    graph.add_node(
        "sales_support_agent",
        lambda state: sales_support_agent_node(state, deps),
    )
    graph.add_node("fallback_node", fallback_node)

    graph.add_edge(START, "greeting")
    graph.add_edge("greeting", "router")
    graph.add_conditional_edges(
        "router",
        route_from_state,
        {
            "customer_support_agent": "customer_support_agent",
            "tech_support_agent": "tech_support_agent",
            "sales_support_agent": "sales_support_agent",
            "fallback_node": "fallback_node",
        },
    )
    graph.add_edge("customer_support_agent", END)
    graph.add_edge("tech_support_agent", END)
    graph.add_edge("sales_support_agent", END)
    graph.add_edge("fallback_node", END)

    return graph.compile()
