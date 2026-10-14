from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

from data_agent.services import PlatformServices


TOOL_NAMES = (
    "search_data_assets",
    "get_table_metadata",
    "get_column_metadata",
    "get_data_lineage",
    "search_metrics",
    "get_metric_definition",
    "recommend_data_asset",
    "check_permission",
    "batch_check_permission",
    "get_user_roles",
    "get_role_detail",
    "get_permission_history",
    "recommend_permission",
    "create_permission_ticket",
    "get_ticket_status",
    "parse_sql",
    "get_table_ddl",
    "get_indexes",
    "get_statistics",
    "explain_sql",
    "validate_sql",
    "optimize_sql",
    "rewrite_sql",
    "execute_query",
    "get_query_status",
    "get_query_result",
    "cancel_query",
    "get_ticket_context",
    "check_duplicate_permission",
    "analyze_risk",
    "get_approval_history",
    "generate_dag",
    "validate_dag",
    "submit_dag",
    "trigger_dag",
    "get_dag_status",
    "backfill_dag",
)

# 新平台能力按需注册，旧适配器无需实现；执行仍经过同一审计入口。
OPTIONAL_TOOL_NAMES = ("get_job_metrics", "search_logs", "get_query_profile")


@dataclass(frozen=True)
class ToolExecution:
    tool: str
    result: Any
    audit_event: dict[str, Any]


class ToolRegistry:
    def __init__(
        self,
        services: PlatformServices,
        audit_sink: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        """作用：负责 `__init__` 对应的处理。
        上游：PlatformAPIError.__init__。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        self._services = services
        self._audit_sink = audit_sink
        self._tools = {
            name: getattr(services, name)
            for name in (*TOOL_NAMES, *OPTIONAL_TOOL_NAMES)
            if callable(getattr(services, name, None))
            and (name in TOOL_NAMES or name in getattr(services, "supported_optional_tools", OPTIONAL_TOOL_NAMES))
        }
        missing = sorted(set(TOOL_NAMES) - set(self._tools))
        if missing:
            raise TypeError(f"Platform adapter is missing tools: {', '.join(missing)}")

    @property
    def names(self) -> tuple[str, ...]:

        """作用：负责 `names` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return tuple(sorted(self._tools))

    def record_candidate_rejection(self, *, user_id: str, session_id: str, task_id: str, intent: str | None, stage: str, code: str) -> dict[str, Any]:
        """记录模型候选拒绝原因，不保存候选参数或敏感正文。"""
        event = {
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "user_id": user_id, "session_id": session_id, "task_id": task_id,
            "intent": intent, "stage": stage, "contract_version": "1",
            "candidate_validation": "rejected", "error_code": code,
            "execution_status": "not_started",
        }
        if self._audit_sink:
            self._audit_sink(event)
        return event

    def invoke(
        self,
        tool: str,
        request: dict[str, Any],
        *,
        user_id: str,
        session_id: str,
        task_id: str,
        intent: str | None = None,
        audit_context: dict[str, Any] | None = None,
    ) -> ToolExecution:
        """作用：负责 `invoke` 对应的处理。
        上游：DataAgentRuntime.chat, DataAgentRuntime.resume, LlmIntentRouter.route, ToolBatch.call。
        下游：_audit_event。
        """
        if tool not in self._tools:
            raise KeyError(f"Unknown platform tool: {tool}")
        started = time.perf_counter()
        result: Any = None
        error: str | None = None
        try:
            binder = getattr(self._services, "bind_user", None)
            if callable(binder):
                with binder(user_id):
                    result = self._tools[tool](**request)
            else:
                result = self._tools[tool](**request)
            return ToolExecution(
                tool=tool,
                result=result,
                audit_event=self._audit_event(
                    user_id=user_id,
                    session_id=session_id,
                    task_id=task_id,
                    intent=intent,
                    tool=tool,
                    request=request,
                    response=result,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=None,
                    audit_context=audit_context,
                ),
            )
        except Exception as exc:
            error = str(exc)
            raise
        finally:
            if error:
                event = self._audit_event(
                    user_id=user_id,
                    session_id=session_id,
                    task_id=task_id,
                    intent=intent,
                    tool=tool,
                    request=request,
                    response=None,
                    latency_ms=(time.perf_counter() - started) * 1000,
                    error=error,
                    audit_context=audit_context,
                )
                if self._audit_sink:
                    self._audit_sink(event)

    def _audit_event(self, **kwargs: Any) -> dict[str, Any]:
        """作用：负责 `_audit_event` 对应的处理。
        上游：ToolRegistry.invoke。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        request = kwargs["request"]
        response = kwargs["response"]
        sql = request.get("sql")
        permission_check = response if kwargs["tool"] == "check_permission" else None
        ticket_id = None
        query_id = None
        if isinstance(response, dict):
            ticket_id = response.get("ticket_id")
            query_id = response.get("query_id")
        event = {
            "timestamp": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds"),
            "user_id": kwargs["user_id"],
            "session_id": kwargs["session_id"],
            "task_id": kwargs["task_id"],
            "intent": kwargs["intent"],
            "tool": kwargs["tool"],
            "request": request,
            "response": response,
            "sql": sql,
            "permission_check": permission_check,
            "ticket_id": ticket_id,
            "query_id": query_id,
            "latency_ms": round(kwargs["latency_ms"], 3),
            "error": kwargs["error"],
        }
        # audit_context 只记录服务端确定的阶段和契约版本，不接受模型自报字段。
        event.update(kwargs.get("audit_context") or {})
        if self._audit_sink:
            self._audit_sink(event)
        return event


class ToolBatch:
    """Collect state updates for tool calls made by one graph node."""

    def __init__(
        self,
        registry: ToolRegistry,
        *,
        user_id: str,
        session_id: str,
        task_id: str,
        intent: str | None,
    ) -> None:
        """作用：负责 `__init__` 对应的处理。
        上游：PlatformAPIError.__init__。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        self.registry = registry
        self.user_id = user_id
        self.session_id = session_id
        self.task_id = task_id
        self.intent = intent
        self.events: list[dict[str, Any]] = []
        self.names: list[str] = []

    def call(self, tool: str, **request: Any) -> Any:
        """作用：负责 `call` 对应的处理。
        上游：AgentNodes._load_sql_context, AgentNodes.analyze_sql, AgentNodes.apply_permission, AgentNodes.approval_context, AgentNodes.approval_risk, AgentNodes.backfill_dag, AgentNodes.check_permission, AgentNodes.dag_status, AgentNodes.discover_assets, AgentNodes.execute_query, AgentNodes.explain_columns, AgentNodes.explain_metric, AgentNodes.explain_query_result, AgentNodes.explain_role, AgentNodes.explain_table, AgentNodes.generate_dag, AgentNodes.optimize_sql, AgentNodes.permission_history, AgentNodes.prepare_query, AgentNodes.submit_dag, AgentNodes.ticket_status, AgentNodes.trigger_dag, AgentNodes.validate_dag。
        下游：invoke。
        """
        execution = self.registry.invoke(
            tool,
            request,
            user_id=self.user_id,
            session_id=self.session_id,
            task_id=self.task_id,
            intent=self.intent,
        )
        self.events.append(execution.audit_event)
        self.names.append(tool)
        return execution.result

    def state_update(self) -> dict[str, Any]:
        """作用：负责 `state_update` 对应的处理。
        上游：AgentNodes.analyze_sql, AgentNodes.apply_permission, AgentNodes.approval_context, AgentNodes.approval_risk, AgentNodes.backfill_dag, AgentNodes.check_permission, AgentNodes.dag_status, AgentNodes.discover_assets, AgentNodes.execute_query, AgentNodes.explain_columns, AgentNodes.explain_metric, AgentNodes.explain_query_result, AgentNodes.explain_role, AgentNodes.explain_table, AgentNodes.generate_dag, AgentNodes.optimize_sql, AgentNodes.permission_history, AgentNodes.prepare_query, AgentNodes.submit_dag, AgentNodes.ticket_status, AgentNodes.trigger_dag, AgentNodes.validate_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return {
            "audit_events": self.events,
            "tool_calls": self.names,
        }
