from __future__ import annotations

from typing import Any, Callable

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command

from data_agent.models import Intent
from data_agent.nodes import AgentNodes
from data_agent.routing import IntentRouter
from data_agent.services import PlatformServices
from data_agent.state import AgentState
from data_agent.tooling import ToolRegistry


INTENT_TO_NODE = {
    Intent.DATA_DISCOVERY.value: "discover_assets",
    Intent.TABLE_EXPLAIN.value: "explain_table",
    Intent.COLUMN_EXPLAIN.value: "explain_columns",
    Intent.METRIC_EXPLAIN.value: "explain_metric",
    Intent.PERMISSION_CHECK.value: "check_permission",
    Intent.PERMISSION_APPLY.value: "apply_permission",
    Intent.PERMISSION_HISTORY.value: "permission_history",
    Intent.TICKET_STATUS.value: "ticket_status",
    Intent.ROLE_EXPLAIN.value: "explain_role",
    Intent.SQL_ANALYZE.value: "analyze_sql",
    Intent.SQL_OPTIMIZE.value: "optimize_sql",
    Intent.SQL_REWRITE.value: "rewrite_sql",
    Intent.QUERY_EXECUTE.value: "prepare_query",
    Intent.QUERY_EXPLAIN.value: "explain_query_result",
    Intent.APPROVAL_CONTEXT.value: "approval_context",
    Intent.APPROVAL_RISK.value: "approval_risk",
    Intent.UNKNOWN.value: "unknown",
}


def build_data_agent_graph(
    services: PlatformServices,
    *,
    checkpointer: BaseCheckpointSaver | None = None,
    audit_sink: Callable[[dict[str, Any]], None] | None = None,
    router: IntentRouter | None = None,
):
    registry = ToolRegistry(services, audit_sink=audit_sink)
    nodes = AgentNodes(registry, router=router)
    builder = StateGraph(AgentState)

    builder.add_node("prepare", nodes.prepare)
    builder.add_node("route", nodes.route)
    builder.add_node("discover_assets", nodes.discover_assets)
    builder.add_node("explain_table", nodes.explain_table)
    builder.add_node("explain_columns", nodes.explain_columns)
    builder.add_node("explain_metric", nodes.explain_metric)
    builder.add_node("check_permission", nodes.check_permission)
    builder.add_node("apply_permission", nodes.apply_permission)
    builder.add_node("permission_history", nodes.permission_history)
    builder.add_node("ticket_status", nodes.ticket_status)
    builder.add_node("explain_role", nodes.explain_role)
    builder.add_node("analyze_sql", nodes.analyze_sql)
    builder.add_node("optimize_sql", nodes.optimize_sql)
    builder.add_node("rewrite_sql", nodes.rewrite_sql)
    builder.add_node("prepare_query", nodes.prepare_query)
    builder.add_node("execute_query", nodes.execute_query)
    builder.add_node("explain_query_result", nodes.explain_query_result)
    builder.add_node("approval_context", nodes.approval_context)
    builder.add_node("approval_risk", nodes.approval_risk)
    builder.add_node("unknown", nodes.unknown)
    builder.add_node("finalize", nodes.finalize)

    builder.add_edge(START, "prepare")
    builder.add_edge("prepare", "route")
    builder.add_conditional_edges("route", _route_intent, INTENT_TO_NODE)

    for node in (
        "discover_assets",
        "explain_table",
        "explain_columns",
        "explain_metric",
        "apply_permission",
        "permission_history",
        "explain_role",
        "analyze_sql",
        "optimize_sql",
        "rewrite_sql",
        "explain_query_result",
        "approval_context",
        "approval_risk",
        "unknown",
    ):
        builder.add_edge(node, "finalize")

    builder.add_conditional_edges(
        "check_permission",
        _after_permission_check,
        {
            "request_permission": "apply_permission",
            "finish": "finalize",
        },
    )
    builder.add_conditional_edges(
        "ticket_status",
        _after_ticket_status,
        {
            "continue_query": "prepare_query",
            "finish": "finalize",
        },
    )
    builder.add_conditional_edges(
        "prepare_query",
        _after_query_prepare,
        {
            "execute": "execute_query",
            "request_permission": "apply_permission",
            "finish": "finalize",
        },
    )
    builder.add_edge("execute_query", "finalize")
    builder.add_edge("finalize", END)

    return builder.compile(checkpointer=checkpointer or MemorySaver())


def _route_intent(state: AgentState) -> str:
    return state.get("intent", Intent.UNKNOWN.value)


def _after_query_prepare(state: AgentState) -> str:
    if state.get("_query_ready"):
        return "execute"
    if state.get("_permission_offer_required"):
        return "request_permission"
    return "finish"


def _after_permission_check(state: AgentState) -> str:
    return (
        "request_permission"
        if state.get("_permission_offer_required")
        else "finish"
    )


def _after_ticket_status(state: AgentState) -> str:
    return "continue_query" if state.get("_continue_query") else "finish"


class DataAgentRuntime:
    """Thin API around the compiled graph for CLI and service integrations."""

    def __init__(
        self,
        services: PlatformServices,
        *,
        checkpointer: BaseCheckpointSaver | None = None,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
        router: IntentRouter | None = None,
    ) -> None:
        self.graph = build_data_agent_graph(
            services,
            checkpointer=checkpointer,
            audit_sink=audit_sink,
            router=router,
        )
        self._configs: dict[str, dict[str, Any]] = {}

    def chat(
        self,
        *,
        user_id: str,
        session_id: str,
        message: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        config = self._config(session_id)
        result = self.graph.invoke(
            {
                "user_id": user_id,
                "session_id": session_id,
                "message": message,
                "context": context or {},
                "messages": [{"role": "user", "content": message}],
            },
            config=config,
        )
        return self._turn_result(result)

    def resume(
        self,
        *,
        session_id: str,
        approved: bool | None = None,
        decision: Any | None = None,
    ) -> dict[str, Any]:
        if decision is None:
            decision = {"approved": bool(approved)}
        result = self.graph.invoke(
            Command(resume=decision),
            config=self._config(session_id),
        )
        return self._turn_result(result)

    def get_state(self, *, session_id: str) -> dict[str, Any]:
        snapshot = self.graph.get_state(self._config(session_id))
        return dict(snapshot.values)

    @staticmethod
    def _turn_result(result: dict[str, Any]) -> dict[str, Any]:
        if "__interrupt__" in result:
            interrupts = result["__interrupt__"]
            value = interrupts[0].value if interrupts else {}
            return {
                "status": "interrupted",
                "interrupt": value,
                "state": result,
            }
        return {
            "status": "completed",
            "response": result.get("response", {}),
            "intent": result.get("intent"),
            "tool_calls": result.get("tool_calls", []),
            "audit_events": result.get("audit_events", []),
            "state": result,
        }

    def _config(self, session_id: str) -> dict[str, Any]:
        if session_id not in self._configs:
            self._configs[session_id] = {
                "configurable": {"thread_id": session_id}
            }
        return self._configs[session_id]
