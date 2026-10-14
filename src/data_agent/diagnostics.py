"""基于查询与计算平台证据的保守诊断。"""

from __future__ import annotations

from typing import Any

from data_agent.tooling import ToolRegistry


class DiagnosisAgent:
    def __init__(self, registry: ToolRegistry) -> None:
        """保留统一工具注册器，使诊断调用进入同一审计链。"""
        self.registry = registry

    def _call(self, name: str, arguments: dict[str, Any], *, user_id: str, session_id: str, task_id: str) -> Any:
        """通过统一工具入口查询平台事实，保留审计和当前用户身份。"""
        return self.registry.invoke(name, arguments, user_id=user_id, session_id=session_id, task_id=task_id, intent="diagnosis").result

    def query(self, query_id: str, *, user_id: str, session_id: str, task_id: str) -> dict[str, Any]:
        """先核对查询归属，再使用执行计划给出有条件的诊断。"""
        status = self._call("get_query_status", {"query_id": query_id}, user_id=user_id, session_id=session_id, task_id=task_id)
        evidence: dict[str, Any] = {"query_id": query_id, "status": status.get("status")}
        if status.get("status") == "not_found" or status.get("user_id") != user_id:
            return {"status": "insufficient_evidence", "confidence": "none", "causes": [], "evidence": evidence, "limitations": ["查询不存在或当前用户无权查看"]}
        sql = status.get("sql")
        if not sql:
            return {"status": "insufficient_evidence", "confidence": "none", "causes": [], "evidence": evidence, "limitations": ["平台未返回该查询的 SQL 和执行计划"]}
        plan = self._call("explain_sql", {"sql": sql}, user_id=user_id, session_id=session_id, task_id=task_id)
        evidence["plan"] = plan
        causes: list[dict[str, str]] = []
        if plan.get("has_full_scan"):
            causes.append({"candidate": "存在全表扫描", "basis": "EXPLAIN 标记了全表扫描", "next_check": "确认分区过滤、扫描量和执行时段"})
        return {
            "status": "diagnosed",
            "confidence": "low",
            "causes": causes,
            "evidence": evidence,
            "limitations": ["尚无运行指标和日志，不能仅凭计划确认根因"],
        }

    def job(self, dag_id: str, *, user_id: str, session_id: str, task_id: str) -> dict[str, Any]:
        """读取 DAG 状态；缺少运行日志和指标时不猜测失败根因。"""
        status = self._call("get_dag_status", {"dag_id": dag_id}, user_id=user_id, session_id=session_id, task_id=task_id)
        run_id = status.get("last_run_id")
        if run_id and {"get_job_metrics", "search_logs"}.issubset(self.registry.names):
            metrics = self._call("get_job_metrics", {"dag_id": dag_id}, user_id=user_id, session_id=session_id, task_id=task_id)
            logs = self._call("search_logs", {"resource_type": "job", "resource_id": run_id, "limit": 100}, user_id=user_id, session_id=session_id, task_id=task_id)
            # 只有日志和指标属于同一运行实例，才能共同支持候选根因。
            if metrics.get("run_id") == run_id and logs.get("run_id") == run_id:
                lines = logs.get("lines", [])
                log_text = "\n".join(str(line) for line in lines[:100]).lower()
                peak = metrics.get("peak_memory_mb")
                limit = metrics.get("memory_limit_mb")
                if "outofmemory" in log_text and isinstance(peak, (int, float)) and isinstance(limit, (int, float)) and peak >= limit:
                    return {
                        "status": "diagnosed", "confidence": "medium",
                        "causes": [{"candidate": "内存不足", "basis": "同一运行日志出现 OutOfMemory，峰值内存达到配额", "next_check": "检查数据倾斜、分区大小及 Executor 内存"}],
                        "evidence": {"dag_id": dag_id, "job_status": status, "metrics": metrics, "log_excerpt": lines[:10]},
                        "limitations": ["需在受控环境验证资源调整后的运行结果"],
                    }
        return {
            "status": "insufficient_evidence",
            "confidence": "none",
            "causes": [],
            "evidence": {"dag_id": dag_id, "job_status": status},
            "limitations": ["仅有任务状态，尚未接入本次运行的日志、指标与近期变更"],
        }
