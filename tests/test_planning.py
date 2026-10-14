import pytest

from data_agent.adapters.memory import InMemoryPlatformAdapter
from data_agent.planning import Plan, PlanRunner, PlanStep, PlanValidationError
from data_agent.tool_harness import ToolHarness
from data_agent.tooling import ToolRegistry


def test_plan_validates_dependencies_and_runs_read_only_steps() -> None:
    plan = Plan(steps=[
        PlanStep(step_id="search", tool="search_data_assets", arguments={"query": "订单", "limit": 1}),
        PlanStep(step_id="metadata", tool="get_table_metadata", depends_on=["search"], arguments={"table": {"from_step": "search", "path": ["assets", 0, "qualified_name"]}}),
    ])
    run = PlanRunner(ToolHarness(ToolRegistry(InMemoryPlatformAdapter()))).run(plan, user_id="u_1001", session_id="s1", task_id="t1")
    assert run.status == "succeeded"
    assert run.results["metadata"]["found"] is True
    assert run.trace[0]["step_id"] == "search"


@pytest.mark.parametrize("steps", [
    [PlanStep(step_id="a", tool="search_data_assets", arguments={"query": "x"}, depends_on=["missing"])],
    [PlanStep(step_id="a", tool="search_data_assets", arguments={"query": "x"}, depends_on=["b"]), PlanStep(step_id="b", tool="search_data_assets", arguments={"query": "x"}, depends_on=["a"])],
    [PlanStep(step_id="a", tool="execute_query", arguments={"sql": "select 1"})],
])
def test_plan_rejects_missing_cycle_and_write_or_query_tools(steps) -> None:
    with pytest.raises(PlanValidationError):
        Plan(steps=steps).validate()


def test_plan_budget_blocks_without_tool_execution() -> None:
    plan = Plan(steps=[PlanStep(step_id="a", tool="search_data_assets", arguments={"query": "x"}), PlanStep(step_id="b", tool="search_data_assets", arguments={"query": "x"})], max_calls=1)
    with pytest.raises(PlanValidationError, match="预算"):
        plan.validate()
