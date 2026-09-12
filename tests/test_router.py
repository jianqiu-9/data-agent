from data_agent.models import Intent
from data_agent.routing import RuleBasedIntentRouter


def test_router_detects_asset_discovery() -> None:
    result = RuleBasedIntentRouter().route("我要查每天销售额，应该用哪张表？")

    assert result.intent == Intent.DATA_DISCOVERY


def test_router_detects_permission_check_and_resource() -> None:
    result = RuleBasedIntentRouter().route("我有 dwd_order 的权限吗？")

    assert result.intent == Intent.PERMISSION_CHECK
    assert result.entities["resource"]["name"] == "dwd_order"


def test_router_detects_sql_optimization() -> None:
    result = RuleBasedIntentRouter().route(
        "这个 SQL 很慢，帮我看看：SELECT * FROM dwd_order WHERE dt='2026-09-01'"
    )

    assert result.intent == Intent.SQL_OPTIMIZE
    assert result.entities["sql"].startswith("SELECT")


def test_router_detects_column_comparison() -> None:
    result = RuleBasedIntentRouter().route(
        "pay_amount 和 settle_amount 有什么区别？"
    )

    assert result.intent == Intent.COLUMN_EXPLAIN
    assert result.entities["columns"] == ["pay_amount", "settle_amount"]


def test_router_accepts_preview_confirmation_text() -> None:
    result = RuleBasedIntentRouter().route(
        "确认提交",
        previous_state={"permission_preview": {"duration_days": 7}},
    )

    assert result.intent == Intent.PERMISSION_APPLY
