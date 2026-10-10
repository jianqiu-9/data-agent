from __future__ import annotations

from typing import Any, Callable, Self

from pydantic import BaseModel, Field

from data_agent.routing import IntentRouter, LlmIntentRouter, RuleBasedIntentRouter


def _as_bool(value: str | bool | None) -> bool:
    """作用：负责 `_as_bool` 对应的处理。
    上游：LLMSettings.from_environment。
    下游：无项目内直接调用（通过参数、属性或外部库完成）。
    """
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class LLMSettings(BaseModel):
    enabled: bool = False
    provider: str = "deepseek"
    model: str = "deepseek-v4-flash"
    api_key: str | None = None
    base_url: str | None = "https://api.deepseek.com"
    temperature: float = Field(default=0.0, ge=0, le=2)
    timeout_seconds: float = Field(default=30.0, gt=0)
    minimum_confidence: float = Field(default=0.55, ge=0, le=1)

    @classmethod
    def from_environment(
        cls,
        environ: dict[str, str] | None = None,
        *,
        prefix: str = "DATA_AGENT_LLM_",
    ) -> Self:
        """作用：负责 `from_environment` 对应的处理。
        上游：HttpPlatformAdapter.from_environment, _add_common_args。
        下游：_as_bool。
        """
        import os

        values = os.environ if environ is None else environ
        api_key = values.get(f"{prefix}API_KEY") or values.get(
            "DEEPSEEK_API_KEY"
        )
        enabled_value = values.get(f"{prefix}ENABLED")
        enabled = (
            _as_bool(enabled_value)
            if enabled_value is not None
            else bool(api_key)
        )
        return cls(
            enabled=enabled,
            provider=values.get(f"{prefix}PROVIDER", "deepseek"),
            model=values.get(f"{prefix}MODEL", "deepseek-v4-flash"),
            api_key=api_key,
            base_url=values.get(
                f"{prefix}BASE_URL", "https://api.deepseek.com"
            ),
            temperature=float(values.get(f"{prefix}TEMPERATURE", "0")),
            timeout_seconds=float(
                values.get(f"{prefix}TIMEOUT_SECONDS", "30")
            ),
            minimum_confidence=float(
                values.get(f"{prefix}MIN_CONFIDENCE", "0.55")
            ),
        )


def create_langchain_chat_model(settings: LLMSettings) -> Any:
    """作用：负责 `create_langchain_chat_model` 对应的处理。
    上游：外部调用方或框架入口（源码中无直接调用点）。
    下游：无项目内直接调用（通过参数、属性或外部库完成）。
    """
    if settings.provider not in {
        "deepseek",
        "openai",
        "openai_compatible",
    }:
        raise ValueError(f"Unsupported LLM provider: {settings.provider}")
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional LLM dependency with "
            "`pip install -e '.[llm]'`"
        ) from exc
    if not settings.api_key:
        raise ValueError(
            "DEEPSEEK_API_KEY or DATA_AGENT_LLM_API_KEY is required "
            "when LLM is enabled"
        )
    kwargs: dict[str, Any] = {
        "model": settings.model,
        "api_key": settings.api_key,
        "temperature": settings.temperature,
        "timeout": settings.timeout_seconds,
    }
    if settings.base_url:
        kwargs["base_url"] = settings.base_url
    return ChatOpenAI(**kwargs)


def build_intent_router(
    settings: LLMSettings,
    *,
    model_factory: Callable[[LLMSettings], Any] | None = None,
) -> IntentRouter:
    """作用：负责 `build_intent_router` 对应的处理。
    上游：_runtime。
    下游：无项目内直接调用（通过参数、属性或外部库完成）。
    """
    if not settings.enabled:
        return RuleBasedIntentRouter()
    factory = model_factory or create_langchain_chat_model
    return LlmIntentRouter(
        factory(settings),
        minimum_confidence=settings.minimum_confidence,
    )
