from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class Intent(StrEnum):
    DATA_DISCOVERY = "data_discovery"
    TABLE_EXPLAIN = "table_explain"
    COLUMN_EXPLAIN = "column_explain"
    METRIC_EXPLAIN = "metric_explain"
    PERMISSION_CHECK = "permission_check"
    PERMISSION_APPLY = "permission_apply"
    PERMISSION_HISTORY = "permission_history"
    TICKET_STATUS = "ticket_status"
    ROLE_EXPLAIN = "role_explain"
    SQL_ANALYZE = "sql_analyze"
    SQL_OPTIMIZE = "sql_optimize"
    SQL_REWRITE = "sql_rewrite"
    QUERY_EXECUTE = "query_execute"
    QUERY_EXPLAIN = "query_explain"
    APPROVAL_CONTEXT = "approval_context"
    APPROVAL_RISK = "approval_risk"
    UNKNOWN = "unknown"


class PermissionAction(StrEnum):
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    DOWNLOAD = "download"


class Environment(StrEnum):
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class ResourceRef(BaseModel):
    type: str = "table"
    database: str = "dw"
    name: str
    field: str | None = None

    @field_validator("name")
    @classmethod
    def clean_name(cls, value: str) -> str:
        return value.strip().strip("`")

    @property
    def qualified_name(self) -> str:
        return f"{self.database}.{self.name}" if self.database else self.name

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class IntentResult(BaseModel):
    intent: Intent
    confidence: float = Field(ge=0, le=1)
    entities: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = ""


class AgentResponse(BaseModel):
    type: str
    answer: str
    cards: list[dict[str, Any]] = Field(default_factory=list)
    actions: list[dict[str, Any]] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class AuditEvent(BaseModel):
    timestamp: datetime
    user_id: str
    session_id: str
    task_id: str
    intent: str | None = None
    tool: str
    request: dict[str, Any]
    response: Any
    latency_ms: float
    error: str | None = None
    sql: str | None = None
    permission_check: dict[str, Any] | None = None
    ticket_id: str | None = None
    query_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
