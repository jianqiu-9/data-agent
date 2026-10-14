from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.diagnostics import DiagnosisAgent
from data_agent.tooling import ToolRegistry


def test_query_diagnosis_uses_status_and_plan_evidence() -> None:
    adapter = InMemoryPlatformAdapter()
    executed = adapter.execute_query("u123", "SELECT dt FROM dw.dws_sales_daily WHERE dt = '2026-09-01'", "prod")
    result = DiagnosisAgent(ToolRegistry(adapter)).query(executed["query_id"], user_id="u123", session_id="s1", task_id="t1")
    assert result["status"] == "diagnosed"
    assert result["evidence"]["query_id"] == executed["query_id"]
    assert result["evidence"]["plan"]["tables"] == ["dw.dws_sales_daily"]
    assert result["confidence"] == "low"


def test_unknown_query_returns_insufficient_evidence() -> None:
    result = DiagnosisAgent(ToolRegistry(InMemoryPlatformAdapter())).query("Qmissing", user_id="u123", session_id="s1", task_id="t1")
    assert result["status"] == "insufficient_evidence"
    assert result["causes"] == []


def test_job_diagnosis_never_claims_root_cause_from_status_alone() -> None:
    result = DiagnosisAgent(ToolRegistry(InMemoryPlatformAdapter(random_seed=1))).job("dag_orders", user_id="u123", session_id="s1", task_id="t1")
    assert result["status"] == "insufficient_evidence"
    assert result["causes"] == []


def test_job_diagnosis_correlates_run_logs_and_metrics() -> None:
    class ObservedAdapter(InMemoryPlatformAdapter):
        def get_job_metrics(self, dag_id):
            return {"run_id": "run-1", "peak_memory_mb": 2048, "memory_limit_mb": 2048}

        def search_logs(self, resource_type, resource_id, limit=100):
            return {"run_id": "run-1", "lines": ["Executor lost: OutOfMemoryError"]}

        def get_dag_status(self, dag_id):
            return {"dag_id": dag_id, "status": "failed", "last_run_id": "run-1"}

    result = DiagnosisAgent(ToolRegistry(ObservedAdapter())).job("dag_orders", user_id="u123", session_id="s1", task_id="t1")
    assert result["status"] == "diagnosed"
    assert result["causes"][0]["candidate"] == "内存不足"
    assert result["confidence"] == "medium"
