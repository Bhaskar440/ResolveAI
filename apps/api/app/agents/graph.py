"""LangGraph wiring: fan-out to Buyer + Merchant, join at Resolution, then gate."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.nodes import (
    AgentState,
    buyer_node,
    merchant_counter_node,
    merchant_node,
    payment_node,
    policy_gate_node,
    resolution_node,
    route_after_resolution,
)


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("buyer", buyer_node)
    builder.add_node("merchant", merchant_node)
    builder.add_node("resolution", resolution_node)
    builder.add_node("merchant_counter", merchant_counter_node)
    builder.add_node("policy_gate", policy_gate_node)
    builder.add_node("payment", payment_node)

    # fan-out: two independent perspectives, no anchoring
    builder.add_edge(START, "buyer")
    builder.add_edge(START, "merchant")

    # join
    builder.add_edge("buyer", "resolution")
    builder.add_edge("merchant", "resolution")

    builder.add_conditional_edges(
        "resolution",
        route_after_resolution,
        {"counter": "merchant_counter", "gate": "policy_gate"},
    )
    builder.add_edge("merchant_counter", "resolution")
    builder.add_edge("policy_gate", "payment")
    builder.add_edge("payment", END)

    return builder.compile()


GRAPH = build_graph()
