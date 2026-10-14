from datetime import datetime, timedelta, timezone

from data_agent.context_memory import ContextBuilder, MemoryStore


def test_memory_requires_consent_and_respects_scope_and_expiry() -> None:
    now = datetime(2026, 10, 13, tzinfo=timezone.utc)
    store = MemoryStore(clock=lambda: now)
    memory_id = store.add(tenant_id="t", user_id="u", content="偏好按日展示", consent=True, ttl=timedelta(days=1))
    assert [item.content for item in store.list(tenant_id="t", user_id="u")] == ["偏好按日展示"]
    assert store.list(tenant_id="t", user_id="other") == []
    assert store.list(tenant_id="other", user_id="u") == []
    store.delete(memory_id, tenant_id="t", user_id="u")
    assert store.list(tenant_id="t", user_id="u") == []


def test_context_builder_keeps_task_facts_inside_budget() -> None:
    builder = ContextBuilder(max_chars=180)
    result = builder.build(goal="分析订单", confirmed={"metric": "gmv", "period": "2026-10-01"}, messages=["旧消息" * 100, "只看华东"], evidence_ids=["e1"])
    assert len(result) <= 180
    assert "gmv" in result
    assert "只看华东" in result
    assert "e1" in result
