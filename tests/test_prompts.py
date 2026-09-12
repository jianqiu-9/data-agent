import pytest

from data_agent.models import Intent
from data_agent.prompts import PROMPT_REGISTRY, SYSTEM_PROMPT, render_prompt


def test_every_intent_has_a_prompt() -> None:
    assert set(PROMPT_REGISTRY) == set(Intent)


@pytest.mark.parametrize("intent", list(Intent))
def test_every_prompt_renders_with_standard_context(intent: Intent) -> None:
    rendered = render_prompt(
        intent,
        message="测试问题",
        user_id="u123",
        session_id="s001",
        context="{}",
        tool_results="{}",
        entities="{}",
        task_state="{}",
    )

    assert rendered.strip()
    assert "$" not in rendered


def test_unknown_prompt_guides_supported_capabilities() -> None:
    rendered = render_prompt(
        Intent.UNKNOWN,
        message="未知请求",
        user_id="u123",
        session_id="s001",
        context="{}",
        tool_results="{}",
        entities="{}",
        task_state="{}",
    )

    assert "权限" in rendered
    assert "SQL" in rendered
    assert "审批" in rendered
    assert SYSTEM_PROMPT in rendered
