import pytest

from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.tool_harness import CandidateError, ToolHarness
from data_agent.tooling import ToolRegistry


def test_harness_executes_valid_candidate_and_records_contract() -> None:
    events = []
    harness = ToolHarness(ToolRegistry(InMemoryPlatformAdapter(), audit_sink=events.append))
    result = harness.execute(
        '{"name":"search_data_assets","arguments":{"query":"订单","limit":2}}',
        allowed={"search_data_assets"},
        stage="discover",
        user_id="u_1001",
        session_id="s1",
        task_id="t1",
    )
    assert result.tool == "search_data_assets"
    assert result.value["assets"]
    assert events[-1]["contract_version"] == "1"
    assert events[-1]["stage"] == "discover"


@pytest.mark.parametrize(
    "candidate, allowed, code",
    [
        ('{"name":"execute_query","arguments":{}}', {"search_data_assets"}, "stage_denied"),
        ('{"name":"search_data_assets","arguments":{"query":"x","user_id":"admin"}}', {"search_data_assets"}, "trusted_field"),
        ('{"name":"search_data_assets","arguments":{"limit":1}}', {"search_data_assets"}, "invalid_arguments"),
        ('{"name":"search_data_assets","arguments":{"query":"x","limit":0}}', {"search_data_assets"}, "invalid_arguments"),
        ('{"name":"search_data_assets","arguments":{"query":"x","extra":1}}', {"search_data_assets"}, "invalid_arguments"),
        ('{"name":"search_data_assets","arguments":{"query":"x"}} {"name":"get_table_metadata"}', {"search_data_assets"}, "invalid_candidate"),
        ("just answer", {"search_data_assets"}, "invalid_candidate"),
    ],
)
def test_harness_rejects_invalid_candidate_before_platform(candidate, allowed, code) -> None:
    class CountingAdapter(InMemoryPlatformAdapter):
        calls = 0

        def search_data_assets(self, query, limit=5):
            self.calls += 1
            return super().search_data_assets(query, limit)

    adapter = CountingAdapter()
    harness = ToolHarness(ToolRegistry(adapter))
    with pytest.raises(CandidateError) as error:
        harness.execute(candidate, allowed=allowed, stage="discover", user_id="u", session_id="s", task_id="t")
    assert error.value.code == code
    assert adapter.calls == 0


def test_harness_enforces_call_budget() -> None:
    harness = ToolHarness(ToolRegistry(InMemoryPlatformAdapter()))
    with pytest.raises(CandidateError, match="预算"):
        harness.execute('{"name":"search_data_assets","arguments":{"query":"订单"}}', allowed={"search_data_assets"}, stage="discover", user_id="u", session_id="s", task_id="t", remaining_calls=0)


def test_harness_binds_selected_resource() -> None:
    harness = ToolHarness(ToolRegistry(InMemoryPlatformAdapter()))
    with pytest.raises(CandidateError) as error:
        harness.execute('{"name":"get_table_metadata","arguments":{"table":"dw.dwd_order"}}', allowed={"get_table_metadata"}, stage="table", user_id="u", session_id="s", task_id="t", required_arguments={"table": "dw.dim_user"})
    assert error.value.code == "policy_denied"


def test_harness_records_rejection_without_candidate_arguments() -> None:
    events = []
    harness = ToolHarness(ToolRegistry(InMemoryPlatformAdapter(), audit_sink=events.append))
    with pytest.raises(CandidateError):
        harness.execute('{"name":"search_data_assets","arguments":{"query":"secret","user_id":"admin"}}', allowed={"search_data_assets"}, stage="discover", user_id="u", session_id="s", task_id="t")
    assert events[0]["candidate_validation"] == "rejected"
    assert events[0]["error_code"] == "trusted_field"
    assert "secret" not in str(events[0])
