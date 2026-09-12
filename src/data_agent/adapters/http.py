from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any
from urllib.parse import quote

import httpx

from data_agent.api_contracts import (
    AnalyzeRiskRequest,
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
    GetIndexesRequest,
    GetPermissionHistoryRequest,
    GetQueryResultRequest,
    GetQueryStatusRequest,
    GetRoleDetailRequest,
    GetStatisticsRequest,
    GetTableDdlRequest,
    GetTicketContextRequest,
    GetTicketStatusRequest,
    GetUserRolesRequest,
    MetricDefinitionRequest,
    OptimizeSqlRequest,
    ParseSqlRequest,
    PlatformSettings,
    RecommendDataAssetRequest,
    RecommendPermissionRequest,
    RewriteSqlRequest,
    SearchDataAssetsRequest,
    SearchMetricsRequest,
    TableMetadataRequest,
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
    USER_ROLES = "/api/v1/users/{user_id}/roles"
    ROLE_DETAIL = "/api/v1/roles/{role_id}"
    PERMISSION_HISTORY = "/api/v1/users/{user_id}/permission-history"
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
    ) -> None:
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

    @classmethod
    def from_environment(cls) -> HttpPlatformAdapter:
        settings = PlatformSettings.from_environment()
        return cls(
            base_url=settings.base_url,
            token=settings.token,
            timeout=settings.timeout_seconds,
            user_agent=settings.user_agent,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __exit__(self, *args: Any) -> None:
        self.close()

    def search_data_assets(self, query: str, limit: int = 5) -> dict[str, Any]:
        request = SearchDataAssetsRequest(query=query, limit=limit)
        return self._get(
            PlatformEndpoints.SEARCH_DATA_ASSETS,
            params=request.payload(),
        )

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        TableMetadataRequest(table=table)
        return self._get(
            PlatformEndpoints.DATA_ASSET_DETAIL.format(table=self._quote(table))
        )

    def get_column_metadata(
        self, table: str, column: str | None = None
    ) -> dict[str, Any]:
        request = ColumnMetadataRequest(table=table, column=column)
        return self._get(
            PlatformEndpoints.DATA_ASSET_COLUMNS.format(
                table=self._quote(table)
            ),
            params={"column": request.column} if request.column else None,
        )

    def get_data_lineage(self, table: str) -> dict[str, Any]:
        DataLineageRequest(table=table)
        return self._get(
            PlatformEndpoints.DATA_ASSET_LINEAGE.format(
                table=self._quote(table)
            )
        )

    def search_metrics(self, query: str, limit: int = 5) -> dict[str, Any]:
        request = SearchMetricsRequest(query=query, limit=limit)
        return self._get(
            PlatformEndpoints.SEARCH_METRICS,
            params=request.payload(),
        )

    def get_metric_definition(self, metric: str) -> dict[str, Any]:
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
        request = CheckPermissionRequest(
            user_id=user_id,
            resource=resource,
            action=action,
            env=env,
        )
        return self._post(
            PlatformEndpoints.CHECK_PERMISSION,
            json=request.payload(),
        )

    def batch_check_permission(
        self, user_id: str, checks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        request = BatchCheckPermissionRequest(
            user_id=user_id,
            checks=[BatchPermissionItem(**item) for item in checks],
        )
        return self._post(
            PlatformEndpoints.BATCH_CHECK_PERMISSION,
            json=request.payload(),
        )

    def get_user_roles(self, user_id: str) -> dict[str, Any]:
        GetUserRolesRequest(user_id=user_id)
        return self._get(
            PlatformEndpoints.USER_ROLES.format(
                user_id=self._quote(user_id)
            )
        )

    def get_role_detail(self, role_id: str) -> dict[str, Any]:
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
        request = GetPermissionHistoryRequest(
            user_id=user_id,
            role_id=role_id,
            resource=resource,
        )
        params = request.payload()
        params.pop("user_id", None)
        if resource:
            params["resource_id"] = self._resource_id(resource)
            params.pop("resource", None)
        return self._get(
            PlatformEndpoints.PERMISSION_HISTORY.format(
                user_id=self._quote(user_id)
            ),
            params=params,
        )

    def recommend_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
        task_goal: str,
    ) -> dict[str, Any]:
        request = RecommendPermissionRequest(
            user_id=user_id,
            resource=resource,
            action=action,
            env=env,
            task_goal=task_goal,
        )
        return self._post(
            PlatformEndpoints.RECOMMEND_PERMISSION,
            json=request.payload(),
        )

    def create_permission_ticket(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        request = CreatePermissionTicketRequest(
            applicant_id=applicant_id,
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
        )

    def get_ticket_status(self, ticket_id: str) -> dict[str, Any]:
        GetTicketStatusRequest(ticket_id=ticket_id)
        return self._get(
            PlatformEndpoints.TICKET_STATUS.format(
                ticket_id=self._quote(ticket_id)
            )
        )

    def parse_sql(self, sql: str) -> dict[str, Any]:
        request = ParseSqlRequest(sql=sql)
        return self._post(
            PlatformEndpoints.PARSE_SQL,
            json=request.payload(),
        )

    def get_table_ddl(self, table: str) -> dict[str, Any]:
        GetTableDdlRequest(table=table)
        return self._get(
            PlatformEndpoints.TABLE_DDL.format(table=self._quote(table))
        )

    def get_indexes(self, table: str) -> dict[str, Any]:
        GetIndexesRequest(table=table)
        return self._get(
            PlatformEndpoints.TABLE_INDEXES.format(
                table=self._quote(table)
            )
        )

    def get_statistics(self, table: str) -> dict[str, Any]:
        GetStatisticsRequest(table=table)
        return self._get(
            PlatformEndpoints.TABLE_STATISTICS.format(
                table=self._quote(table)
            )
        )

    def explain_sql(self, sql: str) -> dict[str, Any]:
        request = ExplainSqlRequest(sql=sql)
        return self._post(
            PlatformEndpoints.EXPLAIN_SQL,
            json=request.payload(),
        )

    def validate_sql(self, sql: str) -> dict[str, Any]:
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
        request = RewriteSqlRequest(sql=sql, context=context or {})
        return self._post(
            PlatformEndpoints.REWRITE_SQL,
            json=request.payload(),
        )

    def execute_query(
        self, user_id: str, sql: str, env: str
    ) -> dict[str, Any]:
        request = ExecuteQueryRequest(
            user_id=user_id,
            sql=sql,
            env=env,
        )
        return self._post(
            PlatformEndpoints.EXECUTE_QUERY,
            json=request.payload(),
        )

    def get_query_status(self, query_id: str) -> dict[str, Any]:
        GetQueryStatusRequest(query_id=query_id)
        return self._get(
            PlatformEndpoints.QUERY_STATUS.format(
                query_id=self._quote(query_id)
            )
        )

    def get_query_result(self, query_id: str) -> dict[str, Any]:
        GetQueryResultRequest(query_id=query_id)
        return self._get(
            PlatformEndpoints.QUERY_RESULT.format(
                query_id=self._quote(query_id)
            )
        )

    def cancel_query(self, query_id: str) -> dict[str, Any]:
        CancelQueryRequest(query_id=query_id)
        return self._post(
            PlatformEndpoints.CANCEL_QUERY.format(
                query_id=self._quote(query_id)
            ),
            json={},
        )

    def get_ticket_context(self, ticket_id: str) -> dict[str, Any]:
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
        request = CheckDuplicatePermissionRequest(
            applicant_id=applicant_id,
            application=application,
        )
        ticket_id = str(application.get("ticket_id", "preview"))
        return self._post(
            PlatformEndpoints.DUPLICATE_PERMISSION.format(
                ticket_id=self._quote(ticket_id)
            ),
            json=request.payload(),
        )

    def analyze_risk(
        self,
        ticket: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        request = AnalyzeRiskRequest(ticket=ticket, context=context)
        ticket_id = str(ticket.get("ticket_id", "preview"))
        return self._post(
            PlatformEndpoints.ANALYZE_RISK.format(
                ticket_id=self._quote(ticket_id)
            ),
            json=request.payload(),
        )

    def get_approval_history(self, ticket_id: str) -> dict[str, Any]:
        GetApprovalHistoryRequest(ticket_id=ticket_id)
        return self._get(
            PlatformEndpoints.APPROVAL_HISTORY.format(
                ticket_id=self._quote(ticket_id)
            )
        )

    def _get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._request("GET", path, params=params)

    def _post(
        self,
        path: str,
        *,
        json: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request("POST", path, json=json)

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = self._client.request(
            method,
            path,
            params=params,
            json=json,
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
        return quote(value, safe="")

    @staticmethod
    def _resource_id(resource: dict[str, Any]) -> str:
        if resource.get("qualified_name"):
            return str(resource["qualified_name"])
        database = str(resource.get("database") or "").strip()
        name = str(resource.get("name") or resource.get("resource") or "").strip()
        return f"{database}.{name}" if database and "." not in name else name
