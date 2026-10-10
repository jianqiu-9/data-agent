from data_agent.adapters.memory import InMemoryPlatformAdapter


def test_dag_mock_returns_structured_random_results() -> None:
    adapter = InMemoryPlatformAdapter(random_seed=42)

    generated = adapter.generate_dag(
        goal="每天同步销售订单",
        schedule="0 2 * * *",
        owner="data-agent",
    )
    validation = adapter.validate_dag(
        dag_definition=generated["dag_definition"],
        env="prod",
    )
    submission = adapter.submit_dag(
        dag_definition=generated["dag_definition"],
        env="prod",
    )
    trigger = adapter.trigger_dag(
        dag_id=generated["dag_id"],
        logical_date="2026-09-25",
    )
    status = adapter.get_dag_status(generated["dag_id"])
    backfill = adapter.backfill_dag(
        dag_id=generated["dag_id"],
        start_date="2026-09-01",
        end_date="2026-09-03",
    )

    assert generated["dag_id"].startswith("dag_")
    assert generated["tasks"]
    assert isinstance(validation["valid"], bool)
    assert submission["status"] in {"queued", "published", "pending"}
    assert trigger["run_id"].startswith("run_")
    assert status["dag_id"] == generated["dag_id"]
    assert backfill["status"] in {"accepted", "running", "queued"}


def test_dag_mock_is_repeatable_when_seeded() -> None:
    first = InMemoryPlatformAdapter(random_seed=7).generate_dag("同步订单")
    second = InMemoryPlatformAdapter(random_seed=7).generate_dag("同步订单")

    assert first == second
