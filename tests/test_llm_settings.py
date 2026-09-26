from data_agent.llm import LLMSettings, build_intent_router
from data_agent.routing import LlmIntentRouter, RuleBasedIntentRouter


def test_llm_settings_load_from_environment() -> None:
    settings = LLMSettings.from_environment(
        {
            "DATA_AGENT_LLM_ENABLED": "true",
            "DATA_AGENT_LLM_PROVIDER": "deepseek",
            "DATA_AGENT_LLM_MODEL": "deepseek-v4-flash",
            "DATA_AGENT_LLM_API_KEY": "secret",
            "DATA_AGENT_LLM_BASE_URL": "https://api.example.com/v1",
            "DATA_AGENT_LLM_TEMPERATURE": "0.1",
            "DATA_AGENT_LLM_TIMEOUT_SECONDS": "20",
            "DATA_AGENT_LLM_MIN_CONFIDENCE": "0.7",
        }
    )

    assert settings.enabled is True
    assert settings.model == "deepseek-v4-flash"
    assert settings.api_key == "secret"
    assert settings.temperature == 0.1
    assert settings.minimum_confidence == 0.7


def test_disabled_llm_uses_rule_router() -> None:
    settings = LLMSettings.from_environment({})

    assert settings.provider == "deepseek"
    assert settings.model == "deepseek-v4-flash"
    assert settings.base_url == "https://api.deepseek.com"
    router = build_intent_router(settings)

    assert isinstance(router, RuleBasedIntentRouter)


def test_enabled_llm_uses_prompt_router() -> None:
    settings = LLMSettings.from_environment(
        {
            "DATA_AGENT_LLM_ENABLED": "true",
            "DATA_AGENT_LLM_MODEL": "test-model",
            "DATA_AGENT_LLM_API_KEY": "secret",
        }
    )
    model = object()

    router = build_intent_router(settings, model_factory=lambda _: model)

    assert isinstance(router, LlmIntentRouter)
    assert router.model is model
    assert router.minimum_confidence == settings.minimum_confidence


def test_deepseek_api_key_is_supported() -> None:
    settings = LLMSettings.from_environment({"DEEPSEEK_API_KEY": "secret"})

    assert settings.api_key == "secret"
    assert settings.enabled is True


def test_explicit_llm_disable_overrides_present_api_key() -> None:
    settings = LLMSettings.from_environment(
        {
            "DEEPSEEK_API_KEY": "secret",
            "DATA_AGENT_LLM_ENABLED": "false",
        }
    )

    assert settings.enabled is False
