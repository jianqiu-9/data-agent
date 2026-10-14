"""受限只读计划的验证与多步骤执行。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from data_agent.tool_harness import READ_TOOL_CONTRACTS, ToolHarness


class PlanValidationError(ValueError):
    """计划结构或安全策略无效。"""


@dataclass(frozen=True)
class PlanStep:
    # step_id 为稳定引用；depends_on 决定执行顺序；arguments 可引用前序输出。
    step_id: str
    tool: str
    arguments: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Plan:
    steps: list[PlanStep]
    max_calls: int = 12

    def validate(self) -> list[PlanStep]:
        """按 DAG 拓扑排序，并拒绝未知依赖、循环和未开放工具。"""
        if not 1 <= len(self.steps) <= 12:
            raise PlanValidationError("计划步骤数必须在 1 到 12 之间")
        if len(self.steps) > self.max_calls:
            raise PlanValidationError("计划超过工具调用预算")
        by_id = {step.step_id: step for step in self.steps}
        if len(by_id) != len(self.steps) or any(not step.step_id for step in self.steps):
            raise PlanValidationError("步骤 ID 缺失或重复")
        for step in self.steps:
            if step.tool not in READ_TOOL_CONTRACTS:
                raise PlanValidationError("计划含未开放工具")
            if any(item not in by_id for item in step.depends_on):
                raise PlanValidationError("计划引用了不存在的依赖")
        # color=1 表示当前访问栈，color=2 表示已排序完成。
        color: dict[str, int] = {}
        ordered: list[PlanStep] = []

        def visit(step_id: str) -> None:
            """深度优先遍历依赖，并用 color 检测环。"""
            if color.get(step_id) == 1:
                raise PlanValidationError("计划存在循环依赖")
            if color.get(step_id) == 2:
                return
            color[step_id] = 1
            step = by_id[step_id]
            for dependency in step.depends_on:
                visit(dependency)
            color[step_id] = 2
            ordered.append(step)

        for step in self.steps:
            visit(step.step_id)
        return ordered


@dataclass(frozen=True)
class PlanRun:
    status: str
    results: dict[str, Any]
    trace: list[dict[str, Any]]
    error: str | None = None


def _resolve(value: Any, *, completed: dict[str, Any], dependencies: list[str]) -> Any:
    """只允许从已完成的直接依赖读取结构化字段，不执行表达式。"""
    if isinstance(value, dict) and set(value) == {"from_step", "path"}:
        source = value["from_step"]
        path = value["path"]
        if source not in dependencies or source not in completed or not isinstance(path, list) or len(path) > 8:
            raise PlanValidationError("步骤参数引用无效")
        current = completed[source]
        try:
            for part in path:
                if isinstance(current, dict) and isinstance(part, str):
                    current = current[part]
                elif isinstance(current, list) and type(part) is int:
                    current = current[part]
                else:
                    raise KeyError(part)
        except (KeyError, IndexError, TypeError) as exc:
            raise PlanValidationError("步骤参数路径不存在") from exc
        return current
    if isinstance(value, dict):
        return {key: _resolve(item, completed=completed, dependencies=dependencies) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, completed=completed, dependencies=dependencies) for item in value]
    return value


class PlanRunner:
    def __init__(self, harness: ToolHarness) -> None:
        """保存工具校验入口，计划步骤不能绕过 Harness。"""
        self.harness = harness

    def run(self, plan: Plan, *, user_id: str, session_id: str, task_id: str) -> PlanRun:
        """按依赖顺序执行受限只读步骤，失败时保留已完成结果。"""
        ordered = plan.validate()
        results: dict[str, Any] = {}
        trace: list[dict[str, Any]] = []
        for step in ordered:
            try:
                arguments = _resolve(step.arguments, completed=results, dependencies=step.depends_on)
                outcome = self.harness.execute(
                    {"name": step.tool, "arguments": arguments},
                    allowed={step.tool},
                    stage=step.step_id,
                    user_id=user_id,
                    session_id=session_id,
                    task_id=task_id,
                    intent="planned_read",
                    remaining_calls=plan.max_calls - len(trace),
                )
            except Exception as exc:
                trace.append({"step_id": step.step_id, "tool": step.tool, "status": "failed", "error_type": type(exc).__name__})
                return PlanRun("partial" if results else "failed", results, trace, str(exc))
            results[step.step_id] = outcome.value
            trace.append({"step_id": step.step_id, "tool": step.tool, "status": "succeeded", "event": outcome.event})
        return PlanRun("succeeded", results, trace)
