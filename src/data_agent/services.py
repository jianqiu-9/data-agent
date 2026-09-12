from __future__ import annotations

from typing import Any, Protocol


class DataCatalogService(Protocol):
    def search_data_assets(self, query: str, limit: int = 5) -> dict[str, Any]: ...

    def get_table_metadata(self, table: str) -> dict[str, Any]: ...

    def get_column_metadata(
        self, table: str, column: str | None = None
    ) -> dict[str, Any]: ...

    def get_data_lineage(self, table: str) -> dict[str, Any]: ...

    def search_metrics(self, query: str, limit: int = 5) -> dict[str, Any]: ...

    def get_metric_definition(self, metric: str) -> dict[str, Any]: ...

    def recommend_data_asset(
        self, goal: str, resources: list[dict[str, Any]] | None = None
    ) -> dict[str, Any]: ...


class PermissionService(Protocol):
    def check_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
    ) -> dict[str, Any]: ...

    def batch_check_permission(
        self, user_id: str, checks: list[dict[str, Any]]
    ) -> dict[str, Any]: ...

    def get_user_roles(self, user_id: str) -> dict[str, Any]: ...

    def get_role_detail(self, role_id: str) -> dict[str, Any]: ...

    def get_permission_history(
        self,
        user_id: str,
        role_id: str | None = None,
        resource: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def recommend_permission(
        self,
        user_id: str,
        resource: dict[str, Any],
        action: str,
        env: str,
        task_goal: str,
    ) -> dict[str, Any]: ...

    def create_permission_ticket(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]: ...

    def get_ticket_status(self, ticket_id: str) -> dict[str, Any]: ...


class SqlService(Protocol):
    def parse_sql(self, sql: str) -> dict[str, Any]: ...

    def get_table_ddl(self, table: str) -> dict[str, Any]: ...

    def get_indexes(self, table: str) -> dict[str, Any]: ...

    def get_statistics(self, table: str) -> dict[str, Any]: ...

    def explain_sql(self, sql: str) -> dict[str, Any]: ...

    def validate_sql(self, sql: str) -> dict[str, Any]: ...

    def optimize_sql(
        self, sql: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...

    def rewrite_sql(
        self, sql: str, context: dict[str, Any] | None = None
    ) -> dict[str, Any]: ...


class QueryService(Protocol):
    def execute_query(
        self, user_id: str, sql: str, env: str
    ) -> dict[str, Any]: ...

    def get_query_status(self, query_id: str) -> dict[str, Any]: ...

    def get_query_result(self, query_id: str) -> dict[str, Any]: ...

    def cancel_query(self, query_id: str) -> dict[str, Any]: ...


class ApprovalService(Protocol):
    def get_ticket_context(self, ticket_id: str) -> dict[str, Any]: ...

    def check_duplicate_permission(
        self, applicant_id: str, application: dict[str, Any]
    ) -> dict[str, Any]: ...

    def analyze_risk(
        self, ticket: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]: ...

    def get_approval_history(self, ticket_id: str) -> dict[str, Any]: ...


class PlatformServices(
    DataCatalogService,
    PermissionService,
    SqlService,
    QueryService,
    ApprovalService,
    Protocol,
):
    """Composite contract implemented by a real platform gateway."""
