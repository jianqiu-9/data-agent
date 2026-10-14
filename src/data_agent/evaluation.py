"""可复现的任务与检索离线评测基础统计。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    expected: Any
    actual: Any


@dataclass(frozen=True)
class EvaluationRun:
    # 版本字段将失败样本与数据、模型、Prompt、工具和索引绑定。
    dataset_version: str
    model_version: str
    prompt_version: str
    tool_version: str
    index_version: str


def evaluate_tasks(cases: list[EvaluationCase], *, run: EvaluationRun) -> dict[str, Any]:
    """按全部有效任务计分；错误、缺答和超时均不会从分母中删除。"""
    if not cases:
        raise ValueError("任务评测集不能为空")
    ids = [case.case_id for case in cases]
    if len(ids) != len(set(ids)):
        raise ValueError("任务样例 ID 重复")
    failed = [case.case_id for case in cases if case.expected != case.actual]
    return {
        "task_success_rate": (len(cases) - len(failed)) / len(cases),
        "total": len(cases),
        "failed_case_ids": failed,
        "versions": {
            "dataset": run.dataset_version,
            "model": run.model_version,
            "prompt": run.prompt_version,
            "tool": run.tool_version,
            "index": run.index_version,
        },
    }


def evaluate_retrieval(expected: dict[str, set[str]], actual: dict[str, list[str]], *, k: int = 5) -> dict[str, Any]:
    """按问题平均 Recall@K，保留未命中问题 ID 便于归因。"""
    if not expected or k < 1:
        raise ValueError("需提供非空检索集和正数 K")
    recalls: list[float] = []
    misses: list[str] = []
    for case_id, relevant in expected.items():
        if not relevant:
            raise ValueError("有答案问题必须标注至少一个证据 ID")
        recalled = set(actual.get(case_id, [])[:k])
        hit_count = len(relevant & recalled)
        recalls.append(hit_count / len(relevant))
        if hit_count < len(relevant):
            misses.append(case_id)
    return {"recall_at_k": sum(recalls) / len(recalls), "total": len(recalls), "missed_case_ids": misses}
