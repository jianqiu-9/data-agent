from langgraph.checkpoint.memory import MemorySaver

from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.graph import DataAgentRuntime


def make_runtime() -> tuple[DataAgentRuntime, InMemoryPlatformAdapter]:
    adapter = InMemoryPlatformAdapter()
    return DataAgentRuntime(adapter, checkpointer=MemorySaver()), adapter


def test_table_explain_uses_catalog_facts() -> None:
    runtime, _ = make_runtime()

    result = runtime.chat(
        user_id="u123",
        session_id="s-table",
        message="dwd_order 是干嘛的？",
    )

    assert result["status"] == "completed"
    assert result["response"]["type"] == "table_explain"
    assert "订单明细表" in result["response"]["answer"]
    assert "get_table_metadata" in result["tool_calls"]


def test_permission_apply_interrupts_then_creates_ticket() -> None:
    runtime, _ = make_runtime()
    first = runtime.chat(
        user_id="u123",
        session_id="s-apply",
        message="帮我申请 dwd_order SELECT 权限 7 天，用于订单分析",
    )

    assert first["status"] == "interrupted"
    assert first["interrupt"]["type"] == "permission_confirmation"
    assert first["interrupt"]["preview"]["duration_days"] == 7

    resumed = runtime.resume(session_id="s-apply", approved=True)

    assert resumed["status"] == "completed"
    assert resumed["response"]["type"] == "permission_apply"
    assert "T202" in resumed["response"]["answer"]
    assert "create_permission_ticket" in resumed["tool_calls"]


def test_query_stops_when_permission_is_missing_and_remembers_task() -> None:
    runtime, _ = make_runtime()
    sql = "SELECT * FROM dwd_order WHERE dt = '2026-09-01'"

    result = runtime.chat(
        user_id="u123",
        session_id="s-query-no-permission",
        message=f"执行一下这个 SQL：{sql}",
    )

    assert result["status"] == "completed"
    assert result["response"]["type"] == "permission_required"
    state = runtime.get_state(session_id="s-query-no-permission")
    assert state["pending_task"]["sql"] == sql
    assert state["pending_task"]["pending_action"] == "query"


def test_query_executes_when_permission_exists() -> None:
    runtime, _ = make_runtime()

    result = runtime.chat(
        user_id="u123",
        session_id="s-query",
        message=(
            "执行一下这个 SQL："
            "SELECT dt, region, order_count, gmv "
            "FROM dw.dws_sales_daily WHERE dt >= '2026-09-01'"
        ),
    )

    assert result["status"] == "completed"
    assert result["response"]["type"] == "query_execute"
    assert "查询状态：succeeded" in result["response"]["answer"]
    assert "execute_query" in result["tool_calls"]


def test_sql_optimizer_uses_explain_and_index_facts() -> None:
    runtime, _ = make_runtime()

    result = runtime.chat(
        user_id="u123",
        session_id="s-sql",
        message=(
            "这个 SQL 很慢：SELECT * FROM dwd_order o "
            "JOIN dim_user u ON o.user_id = u.user_id "
            "WHERE o.dt = '2026-09-01'"
        ),
    )

    assert result["status"] == "completed"
    assert result["response"]["type"] == "sql_optimize"
    assert "idx_dt_user" in result["response"]["answer"]


def test_approval_context_combines_role_history_and_risk() -> None:
    runtime, adapter = make_runtime()
    ticket = adapter.create_permission_ticket(
        "u123",
        {
            "resource": {"database": "dw", "name": "dwd_order"},
            "action": "select",
            "env": "prod",
            "duration_days": 30,
            "reason": "订单分析",
            "role_id": "r_sales_analyst",
        },
    )

    result = runtime.chat(
        user_id="m001",
        session_id="s-approval",
        message=f"审批以下工单的风险：{ticket['ticket_id']}",
    )

    assert result["status"] == "completed"
    assert result["response"]["type"] == "approval_risk"
    assert "销售域数据分析师" in result["response"]["answer"]
    assert "风险等级" in result["response"]["answer"]


def test_approved_ticket_resumes_pending_query() -> None:
    runtime, adapter = make_runtime()
    session_id = "s-resume-query"
    sql = "SELECT * FROM dwd_order WHERE dt = '2026-09-01'"

    blocked = runtime.chat(
        user_id="u123",
        session_id=session_id,
        message=f"执行一下这个 SQL：{sql}",
    )
    assert blocked["response"]["type"] == "permission_required"

    pending = runtime.chat(
        user_id="u123",
        session_id=session_id,
        message="申请",
    )
    assert pending["status"] == "interrupted"
    created = runtime.resume(session_id=session_id, approved=True)
    ticket_id = created["response"]["data"]["ticket"]["ticket_id"]

    adapter.approve_ticket(ticket_id)
    continued = runtime.chat(
        user_id="u123",
        session_id=session_id,
        message=f"工单状态 {ticket_id}",
    )

    assert continued["status"] == "completed"
    assert continued["response"]["type"] == "query_execute"
    assert "查询状态：succeeded" in continued["response"]["answer"]
