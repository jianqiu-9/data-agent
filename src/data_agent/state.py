from __future__ import annotations

import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    user_id: str
    session_id: str
    task_id: str
    message: str
    context: dict[str, Any]
    intent: str
    intent_confidence: float
    entities: dict[str, Any]
    business_goal: str
    identified_resources: list[dict[str, Any]]
    required_permissions: list[dict[str, Any]]
    permission_result: dict[str, Any]
    permission_preview: dict[str, Any]
    permission_recommendation: dict[str, Any]
    ticket: dict[str, Any]
    ticket_status: dict[str, Any]
    pending_task: dict[str, Any]
    generated_sql: str
    sql_context: dict[str, Any]
    sql_analysis: dict[str, Any]
    query_status: dict[str, Any]
    result_reference: dict[str, Any]
    approval_context: dict[str, Any]
    response: dict[str, Any]
    _query_ready: bool
    _continue_query: bool
    messages: Annotated[list[dict[str, Any]], operator.add]
    audit_events: Annotated[list[dict[str, Any]], operator.add]
    tool_calls: Annotated[list[str], operator.add]
    created_at: str
    updated_at: str
