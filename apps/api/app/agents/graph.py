"""LangGraph wiring for the four-agent dispute workflow.

START -> Buyer intake -> (Buyer advocate || Merchant) -> join
join  -> request_info (missing data, stop) | Resolution
Resolution -> (bounded merchant counter) -> policy gate -> Payment -> END

Retries are bounded at the node level. Every LLM node also has a deterministic
fallback, so an unavailable model never blocks a decision.
"""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from langgraph.types import RetryPolicy

from app.agents.nodes import (
    AgentState,
    buyer_intake_node,
    buyer_node,
    join_node,
    merchant_counter_node,
    merchant_node,
    payment_node,
    policy_gate_node,
    request_info_node,
    resolution_node,
    route_after_join,
    route_after_resolution,
)

RETRY = RetryPolicy(max_attempts=2, initial_interval=0.25, backoff_factor=2.0, jitter=True)


def build_graph():
    builder = StateGraph(AgentState)

    builder.add_node("buyer_intake", buyer_intake_node, retry_policy=RETRY)
    builder.add_node("buyer", buyer_node, retry_policy=RETRY)
    builder.add_node("merchant", merchant_node, retry_policy=RETRY)
    builder.add_node("join", join_node)
    builder.add_node("request_info", request_info_node)
    builder.add_node("resolution", resolution_node, retry_policy=RETRY)
    builder.add_node("merchant_counter", merchant_counter_node)
    builder.add_node("policy_gate", policy_gate_node)
    builder.add_node("payment", payment_node)

    # Buyer intake runs once, before either advocate, so both see the same
    # structured facts. Missing information does not stop evidence collection.
    builder.add_edge(START, "buyer_intake")
    builder.add_edge("buyer_intake", "buyer")
    builder.add_edge("buyer_intake", "merchant")

    # Join waits for both advocates before any routing decision.
    builder.add_edge(["buyer", "merchant"], "join")
    builder.add_conditional_edges(
        "join",
        route_after_join,
        {"request_info": "request_info", "resolution": "resolution"},
    )
    builder.add_edge("request_info", END)

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
