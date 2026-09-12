from data_agent.models import Intent
from data_agent.routing import LlmIntentRouter


class FakeModel:
    def __init__(self, content: str) -> None:
        self.content = content
        self.prompts: list[str] = []

    def invoke(self, prompt: str):
        self.prompts.append(prompt)
        return type("Response", (), {"content": self.content})()


def test_llm_router_parses_complete_json_response() -> None:
    model = FakeModel(
        """```json
        {
          "intent": "permission_check",
          "confidence": 0.92,
          "entities": {
            "resource": {"type": "table", "database": "dw", "name": "dwd_order"},
            "action": "select",
            "env": "prod"
          },
          "reasoning": "用户询问权限"
        }
        ```"""
    )

    result = LlmIntentRouter(model).route("dwd_order 有权限吗？")

    assert result.intent == Intent.PERMISSION_CHECK
    assert result.entities["resource"]["name"] == "dwd_order"
    assert "Data Agent" in model.prompts[0]


def test_llm_router_falls_back_when_model_output_is_invalid() -> None:
    model = FakeModel("这不是 JSON")

    result = LlmIntentRouter(model).route("dwd_order 是干嘛的？")

    assert result.intent == Intent.TABLE_EXPLAIN
