from pathlib import Path

from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.graph import DataAgentRuntime
from data_agent.rag import AccessScope, KnowledgeIndex, KnowledgeManifest, KnowledgeQA


def test_knowledge_question_uses_current_authorized_evidence(tmp_path: Path) -> None:
    source = tmp_path / "guide.md"
    source.write_text("# 权限申请\n需要选择角色并填写理由。", encoding="utf-8")
    index = KnowledgeIndex()
    index.ingest(source, KnowledgeManifest(knowledge_base_id="kb", tenant_id="demo", document_id="permission", title="指南", source_uri="kb://permission", version="v1", access_policy_id="readers"))
    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), knowledge_qa=KnowledgeQA(index), access_scope=lambda user: AccessScope("demo", frozenset({"readers"}) if user == "u_1001" else frozenset()))
    allowed = runtime.chat(user_id="u_1001", session_id="s1", message="怎么申请权限？")
    assert allowed["intent"] == "knowledge_qa"
    assert allowed["response"]["data"]["rag_status"] == "retrieved"
    assert allowed["response"]["data"]["citations"][0]["document_id"] == "permission"
    denied = runtime.chat(user_id="u_other", session_id="s2", message="怎么申请权限？")
    assert denied["response"]["data"]["rag_status"] == "insufficient_evidence"


def test_model_candidate_is_constrained_to_discovery_stage() -> None:
    class CandidateModel:
        def invoke(self, prompt):
            return '{"name":"search_data_assets","arguments":{"query":"订单","limit":1}}'

    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), tool_candidate_model=CandidateModel())
    result = runtime.chat(user_id="u_1001", session_id="s1", message="找表 订单")
    assert result["response"]["type"] == "data_discovery"
    assert result["state"]["candidate_call"]["name"] == "search_data_assets"
    assert result["state"]["candidate_validation"]["status"] == "passed"
    assert result["state"]["tool_stage"] == "discover"


def test_invalid_candidate_falls_back_to_fixed_discovery() -> None:
    class CandidateModel:
        def invoke(self, prompt):
            return '{"name":"execute_query","arguments":{}}'

    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), tool_candidate_model=CandidateModel())
    result = runtime.chat(user_id="u_1001", session_id="s1", message="找表 订单")
    assert result["response"]["type"] == "data_discovery"
    assert result["state"]["candidate_validation"]["code"] == "stage_denied"
    assert "execute_query" not in result["tool_calls"]


def test_query_diagnosis_route_returns_platform_evidence() -> None:
    adapter = InMemoryPlatformAdapter()
    query = adapter.execute_query("u123", "SELECT dt FROM dw.dws_sales_daily WHERE dt = '2026-09-01'", "prod")
    runtime = DataAgentRuntime(adapter)
    result = runtime.chat(user_id="u123", session_id="s-diagnose", message=f"排查查询 {query['query_id']} 为什么慢")
    assert result["intent"] == "query_diagnose"
    assert result["response"]["data"]["diagnosis"]["evidence"]["query_id"] == query["query_id"]


def test_data_analysis_executes_authorized_sql_then_verifies_result() -> None:
    runtime = DataAgentRuntime(InMemoryPlatformAdapter())
    result = runtime.chat(
        user_id="u123",
        session_id="s-analysis",
        message="分析这条 SQL：SELECT dt, region, order_count, gmv FROM dw.dws_sales_daily WHERE dt >= '2026-09-01'",
        context={"measures": ["gmv"], "env": "prod"},
    )
    assert result["intent"] == "data_analysis"
    assert result["response"]["data"]["analysis"]["status"] == "verified"
    assert result["response"]["data"]["analysis"]["totals"]["gmv"]


def test_coding_route_uses_injected_generator_and_sandbox() -> None:
    from data_agent.coding import CodingAgent, SandboxResult

    class Generator:
        def generate(self, task):
            return "def transform(rows): return rows"

    class Sandbox:
        def run(self, code, tests):
            return SandboxResult("passed", 0, "ok", "")

    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), coding_agent=CodingAgent(Generator(), Sandbox()), code_tests=lambda goal: "assert True")
    result = runtime.chat(user_id="u123", session_id="s-code", message="生成 Python 数据清洗代码")
    assert result["intent"] == "code_generate"
    assert result["response"]["data"]["coding"]["status"] == "passed"


def test_asset_response_adds_only_mapped_authorized_knowledge(tmp_path: Path) -> None:
    source = tmp_path / "asset.md"
    source.write_text("# 订单表\n订单业务背景说明。", encoding="utf-8")
    index = KnowledgeIndex()
    index.ingest(source, KnowledgeManifest(knowledge_base_id="kb", tenant_id="demo", document_id="asset", title="订单表", source_uri="kb://asset", version="v1", access_policy_id="p", document_type="asset", resource_ids=["dw.dwd_order"]))
    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), knowledge_qa=KnowledgeQA(index), access_scope=lambda user: AccessScope("demo", frozenset({"p"})))
    result = runtime.chat(user_id="u123", session_id="s-asset", message="找表 订单")
    assert result["response"]["data"]["citations"][0]["document_id"] == "asset"
    assert "订单业务背景说明" in result["response"]["answer"]


def test_text_to_sql_generates_validated_draft_without_execution() -> None:
    class SQLModel:
        def invoke(self, prompt):
            return "SELECT dt, order_count FROM dw.dws_sales_daily WHERE dt = '2026-09-01'"

    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), sql_generation_model=SQLModel())
    result = runtime.chat(user_id="u123", session_id="s-text-sql", message="帮我写 SQL 查询每日订单量")
    assert result["intent"] == "text_to_sql"
    assert result["response"]["data"]["draft_status"] == "validated_draft"
    assert "execute_query" not in result["tool_calls"]


def test_text_to_sql_rejects_write_statement() -> None:
    class SQLModel:
        def invoke(self, prompt):
            return "DELETE FROM dw.dwd_order"

    runtime = DataAgentRuntime(InMemoryPlatformAdapter(), sql_generation_model=SQLModel())
    result = runtime.chat(user_id="u123", session_id="s-bad-sql", message="帮我写 SQL 查询订单")
    assert result["response"]["data"]["draft_status"] == "rejected"
    assert "execute_query" not in result["tool_calls"]
