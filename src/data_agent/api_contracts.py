from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field


class ApiRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    def payload(self) -> dict[str, Any]:

        """作用：负责 `payload` 对应的处理。
        上游：HttpPlatformAdapter.analyze_risk, HttpPlatformAdapter.backfill_dag, HttpPlatformAdapter.batch_check_permission, HttpPlatformAdapter.check_duplicate_permission, HttpPlatformAdapter.check_permission, HttpPlatformAdapter.create_permission_ticket, HttpPlatformAdapter.execute_query, HttpPlatformAdapter.explain_sql, HttpPlatformAdapter.generate_dag, HttpPlatformAdapter.get_permission_history, HttpPlatformAdapter.optimize_sql, HttpPlatformAdapter.parse_sql, HttpPlatformAdapter.recommend_data_asset, HttpPlatformAdapter.recommend_permission, HttpPlatformAdapter.rewrite_sql, HttpPlatformAdapter.search_data_assets, HttpPlatformAdapter.search_metrics, HttpPlatformAdapter.submit_dag, HttpPlatformAdapter.trigger_dag, HttpPlatformAdapter.validate_dag, HttpPlatformAdapter.validate_sql。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        return self.model_dump(mode="json", exclude_none=True)


class SearchDataAssetsRequest(ApiRequest):
    query: str
    limit: int = Field(default=5, ge=1, le=50)


class TableMetadataRequest(ApiRequest):
    table: str


class ColumnMetadataRequest(TableMetadataRequest):
    column: str | None = None


class DataLineageRequest(TableMetadataRequest):
    """Request lineage metadata for one table."""


class SearchMetricsRequest(ApiRequest):
    query: str
    limit: int = Field(default=5, ge=1, le=50)


class MetricDefinitionRequest(ApiRequest):
    metric: str


class RecommendDataAssetRequest(ApiRequest):
    goal: str
    resources: list[dict[str, Any]] = Field(default_factory=list)


class CheckPermissionRequest(ApiRequest):
    resource: dict[str, Any]
    action: str = "select"
    env: str = "prod"


class BatchPermissionItem(ApiRequest):
    resource: dict[str, Any]
    action: str = "select"
    env: str = "prod"


class BatchCheckPermissionRequest(ApiRequest):
    checks: list[BatchPermissionItem]


class GetRoleDetailRequest(ApiRequest):
    role_id: str


class GetPermissionHistoryRequest(ApiRequest):
    role_id: str | None = None
    resource: dict[str, Any] | None = None


class RecommendPermissionRequest(ApiRequest):
    resource: dict[str, Any]
    action: str = "select"
    env: str = "prod"
    task_goal: str


class CreatePermissionTicketRequest(ApiRequest):
    role_id: str | None = None
    resource: dict[str, Any]
    action: str = "select"
    env: str = "prod"
    duration_days: int = Field(default=30, ge=1, le=3650)
    reason: str
    approver_id: str | None = None
    auto_fill: bool = True


class GetTicketStatusRequest(ApiRequest):
    ticket_id: str


class ParseSqlRequest(ApiRequest):
    sql: str


class GetTableDdlRequest(ApiRequest):
    table: str


class GetIndexesRequest(ApiRequest):
    table: str


class GetStatisticsRequest(ApiRequest):
    table: str


class ExplainSqlRequest(ApiRequest):
    sql: str


class ValidateSqlRequest(ApiRequest):
    sql: str


class OptimizeSqlRequest(ApiRequest):
    sql: str
    context: dict[str, Any] = Field(default_factory=dict)


class RewriteSqlRequest(OptimizeSqlRequest):
    """Request a behavior-preserving SQL rewrite."""


class ExecuteQueryRequest(ApiRequest):
    sql: str
    env: str = "prod"


class GetQueryStatusRequest(ApiRequest):
    query_id: str


class GetQueryResultRequest(ApiRequest):
    query_id: str


class CancelQueryRequest(ApiRequest):
    query_id: str


class GetTicketContextRequest(ApiRequest):
    ticket_id: str


class CheckDuplicatePermissionRequest(ApiRequest):
    application: dict[str, Any]


class AnalyzeRiskRequest(ApiRequest):
    ticket: dict[str, Any]
    context: dict[str, Any] = Field(default_factory=dict)


class GetApprovalHistoryRequest(ApiRequest):
    ticket_id: str


class GenerateDagRequest(ApiRequest):
    goal: str
    schedule: str | None = None
    owner: str | None = None
    resources: list[dict[str, Any]] = Field(default_factory=list)


class ValidateDagRequest(ApiRequest):
    dag_definition: str
    env: str = "prod"


class SubmitDagRequest(ApiRequest):
    dag_definition: str
    env: str = "prod"


class TriggerDagRequest(ApiRequest):
    dag_id: str
    logical_date: str | None = None
    conf: dict[str, Any] = Field(default_factory=dict)


class GetDagStatusRequest(ApiRequest):
    dag_id: str


class BackfillDagRequest(ApiRequest):
    dag_id: str
    start_date: str
    end_date: str


class PlatformSettings(BaseModel):
    base_url: str
    token: str | None = None
    timeout_seconds: float = Field(default=10.0, gt=0)
    user_agent: str = "data-agent/0.2"

    @classmethod
    def from_environment(
        cls,
        environ: dict[str, str] | None = None,
        *,
        prefix: str = "DATA_PLATFORM_",
    ) -> Self:
        """作用：负责 `from_environment` 对应的处理。
        上游：HttpPlatformAdapter.from_environment, _add_common_args。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        import os

        values = os.environ if environ is None else environ
        base_url = values.get(f"{prefix}BASE_URL", "")
        if not base_url:
            raise ValueError(f"{prefix}BASE_URL is required")
        return cls(
            base_url=base_url,
            token=values.get(f"{prefix}TOKEN"),
            timeout_seconds=float(values.get(f"{prefix}TIMEOUT_SECONDS", "10")),
            user_agent=values.get(
                f"{prefix}USER_AGENT", "data-agent/0.2"
            ),
        )
