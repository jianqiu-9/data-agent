from __future__ import annotations

from contextlib import AbstractContextManager, contextmanager
from contextvars import ContextVar
from typing import Any, Iterator
from urllib.parse import quote

import httpx

from data_agent.api_contracts import (
    AnalyzeRiskRequest,
    BackfillDagRequest,
    BatchCheckPermissionRequest,
    BatchPermissionItem,
    CancelQueryRequest,
    CheckDuplicatePermissionRequest,
    CheckPermissionRequest,
    ColumnMetadataRequest,
    CreatePermissionTicketRequest,
    DataLineageRequest,
    ExecuteQueryRequest,
    ExplainSqlRequest,
    GetApprovalHistoryRequest,
    GetDagStatusRequest,
    GetIndexesRequest,
    GetPermissionHistoryRequest,
    GetQueryResultRequest,
    GetQueryStatusRequest,
    GetRoleDetailRequest,
    GetStatisticsRequest,
    GetTableDdlRequest,
    GetTicketContextRequest,
    GetTicketStatusRequest,
    GenerateDagRequest,
    MetricDefinitionRequest,
    OptimizeSqlRequest,
    ParseSqlRequest,
    PlatformSettings,
    RecommendDataAssetRequest,
    RecommendPermissionRequest,
    SubmitDagRequest,
    RewriteSqlRequest,
    SearchDataAssetsRequest,
    SearchMetricsRequest,
    TableMetadataRequest,
    TriggerDagRequest,
    ValidateDagRequest,
    ValidateSqlRequest,
)


class PlatformAPIError(RuntimeError):
    def __init__(
        self,
        *,
        method: str,
        url: str,
        status_code: int,
        body: str,
    ) -> None:
        """作用：负责 `__init__` 对应的处理。
        上游：PlatformAPIError.__init__。
        下游：__init__。
        """
        super().__init__(
            f"Platform API {method} {url} failed with {status_code}: {body}"
        )
        self.method = method
        self.url = url
        self.status_code = status_code
        self.body = body


class PlatformEndpoints:
    SEARCH_DATA_ASSETS = "/api/v1/data-assets/search"
    DATA_ASSET_DETAIL = "/api/v1/data-assets/{table}"
    DATA_ASSET_COLUMNS = "/api/v1/data-assets/{table}/columns"
    DATA_ASSET_LINEAGE = "/api/v1/data-assets/{table}/lineage"
    SEARCH_METRICS = "/api/v1/metrics/search"
    METRIC_DEFINITION = "/api/v1/metrics/{metric}"
    RECOMMEND_DATA_ASSET = "/api/v1/data-assets/recommend"

    CHECK_PERMISSION = "/api/v1/tools/permission/check"
    BATCH_CHECK_PERMISSION = "/api/v1/tools/permission/batch-check"
    USER_ROLES = "/api/v1/users/me/roles"
    ROLE_DETAIL = "/api/v1/roles/{role_id}"
    PERMISSION_HISTORY = "/api/v1/users/me/permission-history"
    RECOMMEND_PERMISSION = "/api/v1/tools/permission/recommend"
    CREATE_PERMISSION_TICKET = "/api/v1/tools/permission/tickets"
    TICKET_STATUS = "/api/v1/tools/permission/tickets/{ticket_id}"

    PARSE_SQL = "/api/v1/tools/sql/parse"
    TABLE_DDL = "/api/v1/metadata/tables/{table}/ddl"
    TABLE_INDEXES = "/api/v1/metadata/tables/{table}/indexes"
    TABLE_STATISTICS = "/api/v1/metadata/tables/{table}/statistics"
    EXPLAIN_SQL = "/api/v1/tools/sql/explain"
    VALIDATE_SQL = "/api/v1/tools/sql/validate"
    OPTIMIZE_SQL = "/api/v1/tools/sql/optimize"
    REWRITE_SQL = "/api/v1/tools/sql/rewrite"

    EXECUTE_QUERY = "/api/v1/tools/query/execute"
    QUERY_STATUS = "/api/v1/tools/query/{query_id}/status"
    QUERY_RESULT = "/api/v1/tools/query/{query_id}/result"
    CANCEL_QUERY = "/api/v1/tools/query/{query_id}/cancel"

    TICKET_CONTEXT = "/api/v1/tools/approval/tickets/{ticket_id}/context"
    DUPLICATE_PERMISSION = (
        "/api/v1/tools/approval/tickets/{ticket_id}/check-duplicate"
    )
    ANALYZE_RISK = "/api/v1/tools/approval/tickets/{ticket_id}/risk"
    APPROVAL_HISTORY = "/api/v1/tools/approval/tickets/{ticket_id}/history"

    DAG_GENERATE = "/api/v1/dags/generate"
    DAG_VALIDATE = "/api/v1/dags/validate"
    DAG_SUBMIT = "/api/v1/dags"
    DAG_TRIGGER = "/api/v1/dags/{dag_id}/trigger"
    DAG_STATUS = "/api/v1/dags/{dag_id}"
    DAG_BACKFILL = "/api/v1/dags/{dag_id}/backfill"
    JOB_METRICS = "/api/v1/dags/{dag_id}/metrics"
    SEARCH_LOGS = "/api/v1/observability/logs"
    QUERY_PROFILE = "/api/v1/tools/query/{query_id}/profile"


TOOL_ENDPOINTS: dict[str, tuple[str, str]] = {
    "search_data_assets": ("GET", PlatformEndpoints.SEARCH_DATA_ASSETS),
    "get_table_metadata": ("GET", PlatformEndpoints.DATA_ASSET_DETAIL),
    "get_column_metadata": ("GET", PlatformEndpoints.DATA_ASSET_COLUMNS),
    "get_data_lineage": ("GET", PlatformEndpoints.DATA_ASSET_LINEAGE),
    "search_metrics": ("GET", PlatformEndpoints.SEARCH_METRICS),
    "get_metric_definition": ("GET", PlatformEndpoints.METRIC_DEFINITION),
    "recommend_data_asset": ("POST", PlatformEndpoints.RECOMMEND_DATA_ASSET),
    "check_permission": ("POST", PlatformEndpoints.CHECK_PERMISSION),
    "batch_check_permission": (
        "POST",
        PlatformEndpoints.BATCH_CHECK_PERMISSION,
    ),
    "get_user_roles": ("GET", PlatformEndpoints.USER_ROLES),
    "get_role_detail": ("GET", PlatformEndpoints.ROLE_DETAIL),
    "get_permission_history": ("GET", PlatformEndpoints.PERMISSION_HISTORY),
    "recommend_permission": ("POST", PlatformEndpoints.RECOMMEND_PERMISSION),
    "create_permission_ticket": (
        "POST",
        PlatformEndpoints.CREATE_PERMISSION_TICKET,
    ),
    "get_ticket_status": ("GET", PlatformEndpoints.TICKET_STATUS),
    "parse_sql": ("POST", PlatformEndpoints.PARSE_SQL),
    "get_table_ddl": ("GET", PlatformEndpoints.TABLE_DDL),
    "get_indexes": ("GET", PlatformEndpoints.TABLE_INDEXES),
    "get_statistics": ("GET", PlatformEndpoints.TABLE_STATISTICS),
    "explain_sql": ("POST", PlatformEndpoints.EXPLAIN_SQL),
    "validate_sql": ("POST", PlatformEndpoints.VALIDATE_SQL),
    "optimize_sql": ("POST", PlatformEndpoints.OPTIMIZE_SQL),
    "rewrite_sql": ("POST", PlatformEndpoints.REWRITE_SQL),
    "execute_query": ("POST", PlatformEndpoints.EXECUTE_QUERY),
    "get_query_status": ("GET", PlatformEndpoints.QUERY_STATUS),
    "get_query_result": ("GET", PlatformEndpoints.QUERY_RESULT),
    "cancel_query": ("POST", PlatformEndpoints.CANCEL_QUERY),
    "get_ticket_context": ("GET", PlatformEndpoints.TICKET_CONTEXT),
    "check_duplicate_permission": (
        "POST",
        PlatformEndpoints.DUPLICATE_PERMISSION,
    ),
    "analyze_risk": ("POST", PlatformEndpoints.ANALYZE_RISK),
    "get_approval_history": (
        "GET",
        PlatformEndpoints.APPROVAL_HISTORY,
    ),
    "generate_dag": ("POST", PlatformEndpoints.DAG_GENERATE),
    "validate_dag": ("POST", PlatformEndpoints.DAG_VALIDATE),
    "submit_dag": ("POST", PlatformEndpoints.DAG_SUBMIT),
    "trigger_dag": ("POST", PlatformEndpoints.DAG_TRIGGER),
    "get_dag_status": ("GET", PlatformEndpoints.DAG_STATUS),
    "backfill_dag": ("POST", PlatformEndpoints.DAG_BACKFILL),
}


class HttpPlatformAdapter(
    AbstractContextManager["HttpPlatformAdapter"]
):
    """Direct HTTP implementation of every tool used by the LangGraph agent."""

    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 10.0,
        user_agent: str = "data-agent/0.2",
        client: httpx.Client | None = None,
        user_id: str | None = None,
        supported_optional_tools: frozenset[str] = frozenset(),
    ) -> None:
        """作用：负责 `__init__` 对应的处理。
        上游：PlatformAPIError.__init__。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        headers = {"User-Agent": user_agent, "Accept": "application/json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            headers=headers,
        )
        if client is not None:
            self._client.headers.update(headers)
        self._user_id: ContextVar[str | None] = ContextVar(
            f"data_agent_http_user_{id(self)}",
            default=user_id,
        )
        # 只有平台明确声明支持的可选监控工具才进入工具注册表。
        self.supported_optional_tools = supported_optional_tools

    @classmethod
    def from_environment(cls) -> HttpPlatformAdapter:
        """作用：负责 `from_environment` 对应的处理。
        上游：HttpPlatformAdapter.from_environment, _add_common_args。
        下游：from_environment。
        """
        settings = PlatformSettings.from_environment()
        return cls(
            base_url=settings.base_url,
            token=settings.token,
            timeout=settings.timeout_seconds,
            user_agent=settings.user_agent,
        )

    def close(self) -> None:
        """作用：负责 `close` 对应的处理。
        上游：HttpPlatformAdapter.__exit__, HttpPlatformAdapter.close。
        下游：close。
        """
        if self._owns_client:
            self._client.close()

    def __exit__(self, *args: Any) -> None:

        """作用：负责 `__exit__` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：close。
        """
        self.close()

    @contextmanager
    def bind_user(self, user_id: str) -> Iterator[HttpPlatformAdapter]:
        """作用：负责 `bind_user` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        token = self._user_id.set(user_id)
        try:
            yield self
        finally:
            self._user_id.reset(token)

    def search_data_assets(self, query: str, limit: int = 5) -> dict[str, Any]:
        """作用：负责 `search_data_assets` 对应的处理。
        上游：InMemoryPlatformAdapter.recommend_data_asset。
        下游：_get, payload。
        """
        request = SearchDataAssetsRequest(query=query, limit=limit)
        return self._get(
            PlatformEndpoints.SEARCH_DATA_ASSETS,
            params=request.payload(),
        )

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_table_metadata` 对应的处理。
        上游：InMemoryPlatformAdapter.analyze_risk, InMemoryPlatformAdapter.get_column_metadata, InMemoryPlatformAdapter.get_table_ddl, InMemoryPlatformAdapter.recommend_data_asset, InMemoryPlatformAdapter.recommend_permission。
        下游：_get, _quote。
        """
        TableMetadataRequest(table=table)
        return self._get(
            PlatformEndpoints.DATA_ASSET_DETAIL.format(table=self._quote(table))
        )

    def get_column_metadata(
        self, table: str, column: str | None = None
    ) -> dict[str, Any]:
        """作用：负责 `get_column_metadata` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        request = ColumnMetadataRequest(table=table, column=column)
        return self._get(
            PlatformEndpoints.DATA_ASSET_COLUMNS.format(
                table=self._quote(table)
            ),
            params={"column": request.column} if request.column else None,
        )

    def get_data_lineage(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_data_lineage` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        DataLineageRequest(table=table)
        return self._get(
            PlatformEndpoints.DATA_ASSET_LINEAGE.format(
                table=self._quote(table)
            )
        )

    def search_metrics(self, query: str, limit: int = 5) -> dict[str, Any]:
        """作用：负责 `search_metrics` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, payload。
        """
        request = SearchMetricsRequest(query=query, limit=limit)
        return self._get(
            PlatformEndpoints.SEARCH_METRICS,
            params=request.payload(),
        )

    def get_metric_definition(self, metric: str) -> dict[str, Any]:
        """作用：负责 `get_metric_definition` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        MetricDefinitionRequest(metric=metric)
        return self._get(
            PlatformEndpoints.METRIC_DEFINITION.format(
                metric=self._quote(metric)
            )
        )

    def recommend_data_asset(
        self,
        goal: str,
        resources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `recommend_data_asset` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = RecommendDataAssetRequest(
            goal=goal,
            resources=resources or [],
        )
        return self._post(
            PlatformEndpoints.RECOMMEND_DATA_ASSET,
            json=request.payload(),
        )

    def check_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
    ) -> dict[str, Any]:
        """作用：负责 `check_permission` 对应的处理。
        上游：InMemoryPlatformAdapter.batch_check_permission, InMemoryPlatformAdapter.check_duplicate_permission。
        下游：_post, payload。
        """
        request = CheckPermissionRequest(
            resource=resource,
            action=action,
            env=env,
        )
        return self._post(
            PlatformEndpoints.CHECK_PERMISSION,
            json=request.payload(),
            user_id=user_id,
        )

    def batch_check_permission(
        self, user_id: str, checks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """作用：负责 `batch_check_permission` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = BatchCheckPermissionRequest(
            checks=[BatchPermissionItem(**item) for item in checks],
        )
        return self._post(
            PlatformEndpoints.BATCH_CHECK_PERMISSION,
            json=request.payload(),
            user_id=user_id,
        )

    def get_user_roles(self, user_id: str) -> dict[str, Any]:
        """作用：负责 `get_user_roles` 对应的处理。
        上游：InMemoryPlatformAdapter.recommend_permission。
        下游：_get。
        """
        return self._get(
            PlatformEndpoints.USER_ROLES,
            user_id=user_id,
        )

    def get_role_detail(self, role_id: str) -> dict[str, Any]:
        """作用：负责 `get_role_detail` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetRoleDetailRequest(role_id=role_id)
        return self._get(
            PlatformEndpoints.ROLE_DETAIL.format(
                role_id=self._quote(role_id)
            )
        )

    def get_permission_history(
        self,
        user_id: str,
        role_id: str | None = None,
        resource: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `get_permission_history` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：_get, _resource_id, payload。
        """
        request = GetPermissionHistoryRequest(
            role_id=role_id,
            resource=resource,
        )
        params = request.payload()
        if resource:
            params["resource_id"] = self._resource_id(resource)
            params.pop("resource", None)
        return self._get(
            PlatformEndpoints.PERMISSION_HISTORY,
            params=params,
            user_id=user_id,
        )

    def recommend_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
        task_goal: str,
    ) -> dict[str, Any]:
        """作用：负责 `recommend_permission` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = RecommendPermissionRequest(
            resource=resource,
            action=action,
            env=env,
            task_goal=task_goal,
        )
        return self._post(
            PlatformEndpoints.RECOMMEND_PERMISSION,
            json=request.payload(),
            user_id=user_id,
        )

    def create_permission_ticket(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        """作用：负责 `create_permission_ticket` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = CreatePermissionTicketRequest(
            role_id=application.get("role_id"),
            resource=application["resource"],
            action=application.get("action", "select"),
            env=application.get("env", "prod"),
            duration_days=application.get("duration_days", 30),
            reason=application.get("reason", ""),
            approver_id=application.get("approver"),
            auto_fill=application.get("auto_fill", True),
        )
        return self._post(
            PlatformEndpoints.CREATE_PERMISSION_TICKET,
            json=request.payload(),
            user_id=applicant_id,
        )

    def get_ticket_status(self, ticket_id: str) -> dict[str, Any]:
        """作用：负责 `get_ticket_status` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：_get, _quote。
        """
        GetTicketStatusRequest(ticket_id=ticket_id)
        return self._get(
            PlatformEndpoints.TICKET_STATUS.format(
                ticket_id=self._quote(ticket_id)
            )
        )

    def parse_sql(self, sql: str) -> dict[str, Any]:
        """作用：负责 `parse_sql` 对应的处理。
        上游：InMemoryPlatformAdapter.execute_query, InMemoryPlatformAdapter.explain_sql, InMemoryPlatformAdapter.optimize_sql。
        下游：_post, payload。
        """
        request = ParseSqlRequest(sql=sql)
        return self._post(
            PlatformEndpoints.PARSE_SQL,
            json=request.payload(),
        )

    def get_table_ddl(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_table_ddl` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetTableDdlRequest(table=table)
        return self._get(
            PlatformEndpoints.TABLE_DDL.format(table=self._quote(table))
        )

    def get_indexes(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_indexes` 对应的处理。
        上游：InMemoryPlatformAdapter.optimize_sql。
        下游：_get, _quote。
        """
        GetIndexesRequest(table=table)
        return self._get(
            PlatformEndpoints.TABLE_INDEXES.format(
                table=self._quote(table)
            )
        )

    def get_statistics(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_statistics` 对应的处理。
        上游：InMemoryPlatformAdapter.explain_sql。
        下游：_get, _quote。
        """
        GetStatisticsRequest(table=table)
        return self._get(
            PlatformEndpoints.TABLE_STATISTICS.format(
                table=self._quote(table)
            )
        )

    def explain_sql(self, sql: str) -> dict[str, Any]:
        """作用：负责 `explain_sql` 对应的处理。
        上游：InMemoryPlatformAdapter.optimize_sql。
        下游：_post, payload。
        """
        request = ExplainSqlRequest(sql=sql)
        return self._post(
            PlatformEndpoints.EXPLAIN_SQL,
            json=request.payload(),
        )

    def validate_sql(self, sql: str) -> dict[str, Any]:
        """作用：负责 `validate_sql` 对应的处理。
        上游：InMemoryPlatformAdapter.execute_query。
        下游：_post, payload。
        """
        request = ValidateSqlRequest(sql=sql)
        return self._post(
            PlatformEndpoints.VALIDATE_SQL,
            json=request.payload(),
        )

    def optimize_sql(
        self,
        sql: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `optimize_sql` 对应的处理。
        上游：AgentNodes.rewrite_sql, InMemoryPlatformAdapter.rewrite_sql。
        下游：_post, payload。
        """
        request = OptimizeSqlRequest(sql=sql, context=context or {})
        return self._post(
            PlatformEndpoints.OPTIMIZE_SQL,
            json=request.payload(),
        )

    def rewrite_sql(
        self,
        sql: str,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `rewrite_sql` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = RewriteSqlRequest(sql=sql, context=context or {})
        return self._post(
            PlatformEndpoints.REWRITE_SQL,
            json=request.payload(),
        )

    def execute_query(
        self, user_id: str, sql: str, env: str
    ) -> dict[str, Any]:
        """作用：负责 `execute_query` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = ExecuteQueryRequest(
            sql=sql,
            env=env,
        )
        return self._post(
            PlatformEndpoints.EXECUTE_QUERY,
            json=request.payload(),
            user_id=user_id,
        )

    def get_query_status(self, query_id: str) -> dict[str, Any]:
        """作用：负责 `get_query_status` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetQueryStatusRequest(query_id=query_id)
        return self._get(
            PlatformEndpoints.QUERY_STATUS.format(
                query_id=self._quote(query_id)
            )
        )

    def get_query_result(self, query_id: str) -> dict[str, Any]:
        """作用：负责 `get_query_result` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetQueryResultRequest(query_id=query_id)
        return self._get(
            PlatformEndpoints.QUERY_RESULT.format(
                query_id=self._quote(query_id)
            )
        )

    def cancel_query(self, query_id: str) -> dict[str, Any]:
        """作用：负责 `cancel_query` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, _quote。
        """
        CancelQueryRequest(query_id=query_id)
        return self._post(
            PlatformEndpoints.CANCEL_QUERY.format(
                query_id=self._quote(query_id)
            ),
            json={},
        )

    def get_ticket_context(self, ticket_id: str) -> dict[str, Any]:
        """作用：负责 `get_ticket_context` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetTicketContextRequest(ticket_id=ticket_id)
        return self._get(
            PlatformEndpoints.TICKET_CONTEXT.format(
                ticket_id=self._quote(ticket_id)
            )
        )

    def check_duplicate_permission(
        self,
        applicant_id: str,
        application: dict[str, Any],
    ) -> dict[str, Any]:
        """作用：负责 `check_duplicate_permission` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：_post, _quote, payload。
        """
        request = CheckDuplicatePermissionRequest(
            application=application,
        )
        ticket_id = str(application.get("ticket_id", "preview"))
        return self._post(
            PlatformEndpoints.DUPLICATE_PERMISSION.format(
                ticket_id=self._quote(ticket_id)
            ),
            json=request.payload(),
            user_id=applicant_id,
        )

    def analyze_risk(
        self,
        ticket: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """作用：负责 `analyze_risk` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：_post, _quote, payload。
        """
        request = AnalyzeRiskRequest(ticket=ticket, context=context)
        ticket_id = str(ticket.get("ticket_id", "preview"))
        return self._post(
            PlatformEndpoints.ANALYZE_RISK.format(
                ticket_id=self._quote(ticket_id)
            ),
            json=request.payload(),
        )

    def get_approval_history(self, ticket_id: str) -> dict[str, Any]:
        """作用：负责 `get_approval_history` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetApprovalHistoryRequest(ticket_id=ticket_id)
        return self._get(
            PlatformEndpoints.APPROVAL_HISTORY.format(
                ticket_id=self._quote(ticket_id)
            )
        )

    def generate_dag(
        self,
        goal: str,
        schedule: str | None = None,
        owner: str | None = None,
        resources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `generate_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = GenerateDagRequest(
            goal=goal,
            schedule=schedule,
            owner=owner,
            resources=resources or [],
        )
        return self._post(
            PlatformEndpoints.DAG_GENERATE,
            json=request.payload(),
        )

    def validate_dag(
        self,
        dag_definition: str,
        env: str = "prod",
    ) -> dict[str, Any]:
        """作用：负责 `validate_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = ValidateDagRequest(
            dag_definition=dag_definition,
            env=env,
        )
        return self._post(
            PlatformEndpoints.DAG_VALIDATE,
            json=request.payload(),
        )

    def submit_dag(
        self,
        dag_definition: str,
        env: str = "prod",
    ) -> dict[str, Any]:
        """作用：负责 `submit_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, payload。
        """
        request = SubmitDagRequest(
            dag_definition=dag_definition,
            env=env,
        )
        return self._post(
            PlatformEndpoints.DAG_SUBMIT,
            json=request.payload(),
        )

    def trigger_dag(
        self,
        dag_id: str,
        logical_date: str | None = None,
        conf: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `trigger_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, _quote, payload。
        """
        request = TriggerDagRequest(
            dag_id=dag_id,
            logical_date=logical_date,
            conf=conf or {},
        )
        return self._post(
            PlatformEndpoints.DAG_TRIGGER.format(
                dag_id=self._quote(dag_id)
            ),
            json=request.payload(),
        )

    def get_dag_status(self, dag_id: str) -> dict[str, Any]:
        """作用：负责 `get_dag_status` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_get, _quote。
        """
        GetDagStatusRequest(dag_id=dag_id)
        return self._get(
            PlatformEndpoints.DAG_STATUS.format(
                dag_id=self._quote(dag_id)
            )
        )

    def backfill_dag(
        self,
        dag_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """作用：负责 `backfill_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：_post, _quote, payload。
        """
        request = BackfillDagRequest(
            dag_id=dag_id,
            start_date=start_date,
            end_date=end_date,
        )
        return self._post(
            PlatformEndpoints.DAG_BACKFILL.format(
                dag_id=self._quote(dag_id)
            ),
            json=request.payload(),
        )

    def get_job_metrics(self, dag_id: str) -> dict[str, Any]:
        """读取计算任务指标；平台需返回对应 run_id 供诊断关联。"""
        return self._get(PlatformEndpoints.JOB_METRICS.format(dag_id=self._quote(dag_id)))

    def search_logs(self, resource_type: str, resource_id: str, limit: int = 100) -> dict[str, Any]:
        """按任务或查询 ID 查询有限日志，不允许无边界全量读取。"""
        if resource_type not in {"job", "query"} or not 1 <= limit <= 100:
            raise ValueError("日志资源类型或条数无效")
        return self._get(PlatformEndpoints.SEARCH_LOGS, params={"resource_type": resource_type, "resource_id": resource_id, "limit": limit})

    def get_query_profile(self, query_id: str) -> dict[str, Any]:
        """读取查询运行画像，用于区别计划估计与真实执行指标。"""
        return self._get(PlatformEndpoints.QUERY_PROFILE.format(query_id=self._quote(query_id)))

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:

        """作用：负责 `_get` 对应的处理。
        上游：HttpPlatformAdapter.get_approval_history, HttpPlatformAdapter.get_column_metadata, HttpPlatformAdapter.get_dag_status, HttpPlatformAdapter.get_data_lineage, HttpPlatformAdapter.get_indexes, HttpPlatformAdapter.get_metric_definition, HttpPlatformAdapter.get_permission_history, HttpPlatformAdapter.get_query_result, HttpPlatformAdapter.get_query_status, HttpPlatformAdapter.get_role_detail, HttpPlatformAdapter.get_statistics, HttpPlatformAdapter.get_table_ddl, HttpPlatformAdapter.get_table_metadata, HttpPlatformAdapter.get_ticket_context, HttpPlatformAdapter.get_ticket_status, HttpPlatformAdapter.get_user_roles, HttpPlatformAdapter.search_data_assets, HttpPlatformAdapter.search_metrics。
        下游：_request。
        """
        return self._request("GET", path, params=params, user_id=user_id)

    def _post(
        self,
        path: str,
        *,
        json: dict[str, Any],
        user_id: str | None = None,
    ) -> dict[str, Any]:

        """作用：负责 `_post` 对应的处理。
        上游：HttpPlatformAdapter.analyze_risk, HttpPlatformAdapter.backfill_dag, HttpPlatformAdapter.batch_check_permission, HttpPlatformAdapter.cancel_query, HttpPlatformAdapter.check_duplicate_permission, HttpPlatformAdapter.check_permission, HttpPlatformAdapter.create_permission_ticket, HttpPlatformAdapter.execute_query, HttpPlatformAdapter.explain_sql, HttpPlatformAdapter.generate_dag, HttpPlatformAdapter.optimize_sql, HttpPlatformAdapter.parse_sql, HttpPlatformAdapter.recommend_data_asset, HttpPlatformAdapter.recommend_permission, HttpPlatformAdapter.rewrite_sql, HttpPlatformAdapter.submit_dag, HttpPlatformAdapter.trigger_dag, HttpPlatformAdapter.validate_dag, HttpPlatformAdapter.validate_sql。
        下游：_request。
        """
        return self._request("POST", path, json=json, user_id=user_id)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `_request` 对应的处理。
        上游：HttpPlatformAdapter._get, HttpPlatformAdapter._post。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        request_user_id = user_id or self._user_id.get()
        if not request_user_id:
            raise RuntimeError("HTTP platform calls require a user_id")
        response = self._client.request(
            method,
            path,
            params=params,
            json=json,
            headers={"X-User-Id": request_user_id},
        )
        if response.is_error:
            raise PlatformAPIError(
                method=method,
                url=str(response.request.url),
                status_code=response.status_code,
                body=response.text,
            )
        payload = response.json()
        if not isinstance(payload, dict):
            raise TypeError(
                f"Platform API {method} {response.request.url} "
                "must return a JSON object"
            )
        return payload

    @staticmethod
    def _quote(value: str) -> str:

        """作用：负责 `_quote` 对应的处理。
        上游：HttpPlatformAdapter.analyze_risk, HttpPlatformAdapter.backfill_dag, HttpPlatformAdapter.cancel_query, HttpPlatformAdapter.check_duplicate_permission, HttpPlatformAdapter.get_approval_history, HttpPlatformAdapter.get_column_metadata, HttpPlatformAdapter.get_dag_status, HttpPlatformAdapter.get_data_lineage, HttpPlatformAdapter.get_indexes, HttpPlatformAdapter.get_metric_definition, HttpPlatformAdapter.get_query_result, HttpPlatformAdapter.get_query_status, HttpPlatformAdapter.get_role_detail, HttpPlatformAdapter.get_statistics, HttpPlatformAdapter.get_table_ddl, HttpPlatformAdapter.get_table_metadata, HttpPlatformAdapter.get_ticket_context, HttpPlatformAdapter.get_ticket_status, HttpPlatformAdapter.trigger_dag。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return quote(value, safe="")

    @staticmethod
    def _resource_id(resource: dict[str, Any]) -> str:
        """作用：负责 `_resource_id` 对应的处理。
        上游：HttpPlatformAdapter.get_permission_history。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        if resource.get("qualified_name"):
            return str(resource["qualified_name"])
        database = str(resource.get("database") or "").strip()
        name = str(resource.get("name") or resource.get("resource") or "").strip()
        return f"{database}.{name}" if database and "." not in name else name
