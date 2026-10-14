"""阶段受限的模型工具调用入口；平台事实始终由适配器提供。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from data_agent.tooling import ToolRegistry


class _StrictArguments(BaseModel):
    """所有候选业务参数都拒绝模型编造的额外字段。"""

    model_config = ConfigDict(extra="forbid", strict=True)


class SearchAssetsArgs(_StrictArguments):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class TableMetadataArgs(_StrictArguments):
    table: str = Field(min_length=1, max_length=150)


class ColumnMetadataArgs(_StrictArguments):
    table: str = Field(min_length=1, max_length=150)
    column: str | None = Field(default=None, min_length=1, max_length=150)


class SearchMetricsArgs(_StrictArguments):
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class MetricDefinitionArgs(_StrictArguments):
    metric: str = Field(min_length=1, max_length=150)


# 模型可见的工具目录仅收录首期只读工具；新增工具必须先补齐严格参数模型。
READ_TOOL_CONTRACTS: dict[str, type[_StrictArguments]] = {
    "search_data_assets": SearchAssetsArgs,
    "get_table_metadata": TableMetadataArgs,
    "get_column_metadata": ColumnMetadataArgs,
    "search_metrics": SearchMetricsArgs,
    "get_metric_definition": MetricDefinitionArgs,
}
TRUSTED_FIELDS = frozenset({"user_id", "session_id", "task_id", "tenant_id", "approved", "confirmation"})


class CandidateError(ValueError):
    """用稳定错误码区分候选解析、策略与参数错误。"""

    def __init__(self, code: str, message: str) -> None:
        """保存稳定错误码，供调用方和审计定位拒绝原因。"""
        super().__init__(message)
        self.code = code
        self.event: dict[str, Any] | None = None


@dataclass(frozen=True)
class HarnessResult:
    # tool 为实际执行的工具名，value 为适配器返回的事实，event 为审计记录。
    tool: str
    value: Any
    event: dict[str, Any]


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    """拒绝重复 JSON 键，避免验证器和执行器对同一参数理解不同。"""
    value: dict[str, Any] = {}
    for name, item in pairs:
        if name in value:
            raise ValueError("重复的 JSON 字段")
        value[name] = item
    return value


class ToolHarness:
    """校验模型候选调用，成功后才交给平台工具注册器执行。"""

    def __init__(self, registry: ToolRegistry) -> None:
        """绑定现有工具注册器，所有通过校验的调用由它执行。"""
        self.registry = registry

    def schemas(self, allowed: set[str]) -> dict[str, dict[str, Any]]:
        """返回当前阶段的唯一参数 Schema 来源，供模型和校验器共用。"""
        return {name: READ_TOOL_CONTRACTS[name].model_json_schema() for name in sorted(allowed & READ_TOOL_CONTRACTS.keys())}

    def execute(
        self,
        candidate: str | dict[str, Any],
        *,
        allowed: set[str],
        stage: str,
        user_id: str,
        session_id: str,
        task_id: str,
        intent: str | None = None,
        remaining_calls: int = 1,
        required_arguments: dict[str, Any] | None = None,
    ) -> HarnessResult:
        """统一包装拒绝审计；不把未经验证的模型参数写入日志。"""
        try:
            return self._execute(candidate, allowed=allowed, stage=stage, user_id=user_id, session_id=session_id, task_id=task_id, intent=intent, remaining_calls=remaining_calls, required_arguments=required_arguments)
        except CandidateError as exc:
            exc.event = self.registry.record_candidate_rejection(user_id=user_id, session_id=session_id, task_id=task_id, intent=intent, stage=stage, code=exc.code)
            raise

    def _execute(
        self,
        candidate: str | dict[str, Any],
        *,
        allowed: set[str],
        stage: str,
        user_id: str,
        session_id: str,
        task_id: str,
        intent: str | None = None,
        remaining_calls: int = 1,
        required_arguments: dict[str, Any] | None = None,
    ) -> HarnessResult:
        """按解析、阶段、Schema、预算顺序验证；失败时绝不触达适配器。"""
        if remaining_calls <= 0:
            raise CandidateError("budget_exceeded", "本阶段工具调用预算已用完")
        try:
            payload = json.loads(candidate, object_pairs_hook=_unique_pairs) if isinstance(candidate, str) else candidate
        except (ValueError, TypeError) as exc:
            raise CandidateError("invalid_candidate", "候选调用不是单个合法 JSON 对象") from exc
        if not isinstance(payload, dict) or set(payload) != {"name", "arguments"}:
            raise CandidateError("invalid_candidate", "候选调用只能包含 name 和 arguments")
        name = payload["name"]
        arguments = payload["arguments"]
        if not isinstance(name, str) or not isinstance(arguments, dict):
            raise CandidateError("invalid_candidate", "工具名或参数对象格式错误")
        if name not in READ_TOOL_CONTRACTS or name not in allowed:
            raise CandidateError("stage_denied", "当前阶段不允许调用此工具")
        if TRUSTED_FIELDS & arguments.keys():
            raise CandidateError("trusted_field", "模型不能提供服务端身份或确认字段")
        try:
            validated = READ_TOOL_CONTRACTS[name].model_validate(arguments)
        except ValidationError as exc:
            raise CandidateError("invalid_arguments", "工具参数缺失、越界或类型不正确") from exc
        actual_arguments = validated.model_dump()
        if required_arguments and any(actual_arguments.get(key) != value for key, value in required_arguments.items()):
            raise CandidateError("policy_denied", "候选参数与当前任务已确认资源不一致")
        execution = self.registry.invoke(
            name,
            actual_arguments,
            user_id=user_id,
            session_id=session_id,
            task_id=task_id,
            intent=intent,
            audit_context={"stage": stage, "contract_version": "1", "candidate_validation": "passed"},
        )
        return HarnessResult(tool=name, value=execution.result, event=execution.audit_event)
