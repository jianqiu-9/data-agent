from __future__ import annotations

from typing import Any, Protocol


class DataCatalogService(Protocol):
    def search_data_assets(self, query: str, limit: int = 5) -> dict[str, Any]:
        """作用：负责 `search_data_assets` 对应的处理。
        上游：InMemoryPlatformAdapter.recommend_data_asset。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_table_metadata` 对应的处理。
        上游：InMemoryPlatformAdapter.analyze_risk, InMemoryPlatformAdapter.get_column_metadata, InMemoryPlatformAdapter.get_table_ddl, InMemoryPlatformAdapter.recommend_data_asset, InMemoryPlatformAdapter.recommend_permission。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_column_metadata(
        self, table: str, column: str | None = None
    ) -> dict[str, Any]:
        """作用：负责 `get_column_metadata` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_data_lineage(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_data_lineage` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def search_metrics(self, query: str, limit: int = 5) -> dict[str, Any]:
        """作用：负责 `search_metrics` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_metric_definition(self, metric: str) -> dict[str, Any]:
        """作用：负责 `get_metric_definition` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def recommend_data_asset(
        self, goal: str, resources: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]:
        """作用：负责 `recommend_data_asset` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...


class PermissionService(Protocol):
    def check_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
    ) -> dict[str, Any]:
        """作用：负责 `check_permission` 对应的处理。
        上游：InMemoryPlatformAdapter.batch_check_permission, InMemoryPlatformAdapter.check_duplicate_permission。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def batch_check_permission(
        self, user_id: str, checks: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """作用：负责 `batch_check_permission` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_user_roles(self, user_id: str) -> dict[str, Any]:
        """作用：负责 `get_user_roles` 对应的处理。
        上游：InMemoryPlatformAdapter.recommend_permission。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_role_detail(self, role_id: str) -> dict[str, Any]:
        """作用：负责 `get_role_detail` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_permission_history(
        self,
        user_id: str,
        role_id: str | None = None,
        resource: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `get_permission_history` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

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
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def create_permission_ticket(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        """作用：负责 `create_permission_ticket` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_ticket_status(self, ticket_id: str) -> dict[str, Any]:
        """作用：负责 `get_ticket_status` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...


class SqlService(Protocol):
    def parse_sql(self, sql: str) -> dict[str, Any]:
        """作用：负责 `parse_sql` 对应的处理。
        上游：InMemoryPlatformAdapter.execute_query, InMemoryPlatformAdapter.explain_sql, InMemoryPlatformAdapter.optimize_sql。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_table_ddl(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_table_ddl` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_indexes(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_indexes` 对应的处理。
        上游：InMemoryPlatformAdapter.optimize_sql。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_statistics(self, table: str) -> dict[str, Any]:
        """作用：负责 `get_statistics` 对应的处理。
        上游：InMemoryPlatformAdapter.explain_sql。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def explain_sql(self, sql: str) -> dict[str, Any]:
        """作用：负责 `explain_sql` 对应的处理。
        上游：InMemoryPlatformAdapter.optimize_sql。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def validate_sql(self, sql: str) -> dict[str, Any]:
        """作用：负责 `validate_sql` 对应的处理。
        上游：InMemoryPlatformAdapter.execute_query。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def optimize_sql(
        self, sql: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """作用：负责 `optimize_sql` 对应的处理。
        上游：AgentNodes.rewrite_sql, InMemoryPlatformAdapter.rewrite_sql。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def rewrite_sql(
        self, sql: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """作用：负责 `rewrite_sql` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...


class QueryService(Protocol):
    def execute_query(
        self, user_id: str, sql: str, env: str
    ) -> dict[str, Any]:
        """作用：负责 `execute_query` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_query_status(self, query_id: str) -> dict[str, Any]:
        """作用：负责 `get_query_status` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_query_result(self, query_id: str) -> dict[str, Any]:
        """作用：负责 `get_query_result` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def cancel_query(self, query_id: str) -> dict[str, Any]:
        """作用：负责 `cancel_query` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...


class ApprovalService(Protocol):
    def get_ticket_context(self, ticket_id: str) -> dict[str, Any]:
        """作用：负责 `get_ticket_context` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def check_duplicate_permission(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]:
        """作用：负责 `check_duplicate_permission` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def analyze_risk(
        self, ticket: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        """作用：负责 `analyze_risk` 对应的处理。
        上游：InMemoryPlatformAdapter.get_ticket_context。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_approval_history(self, ticket_id: str) -> dict[str, Any]:
        """作用：负责 `get_approval_history` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...


class WorkflowService(Protocol):
    def generate_dag(
        self,
        goal: str,
        schedule: str | None = None,
        owner: str | None = None,
        resources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `generate_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def validate_dag(
        self,
        dag_definition: str,
        env: str = "prod",
    ) -> dict[str, Any]:
        """作用：负责 `validate_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def submit_dag(
        self,
        dag_definition: str,
        env: str = "prod",
    ) -> dict[str, Any]:
        """作用：负责 `submit_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def trigger_dag(
        self,
        dag_id: str,
        logical_date: str | None = None,
        conf: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """作用：负责 `trigger_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def get_dag_status(self, dag_id: str) -> dict[str, Any]:
        """作用：负责 `get_dag_status` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...

    def backfill_dag(
        self,
        dag_id: str,
        start_date: str,
        end_date: str,
    ) -> dict[str, Any]:
        """作用：负责 `backfill_dag` 对应的处理。
        上游：外部调用方或框架入口（源码中无直接调用点）。
        下游：无项目内直接调用（通过参数、属性或外部库完成）。
        """
        ...


class PlatformServices(
    DataCatalogService,
    PermissionService,
    SqlService,
    QueryService,
    ApprovalService,
    WorkflowService,
    Protocol,
):
    """Composite contract implemented by a real platform gateway."""
