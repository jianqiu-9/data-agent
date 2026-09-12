from __future__ import annotations

from typing import Any, Callable, Self

from pydantic import BaseModel, Field

from data_agent.routing import IntentRouter, LlmIntentRouter, RuleBasedIntentRouter


def _as_bool(value: str | bool | None) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class LLMSettings(BaseModel):
    enabled: bool = False
    provider: str = "openai"
    model: str = "gpt-5"
    api_key: str | None = None
    base_url: str | None = None
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
        import os

        values = os.environ if environ is None else environ
        return cls(
            enabled=_as_bool(values.get(f"{prefix}ENABLED", "false")),
            provider=values.get(f"{prefix}PROVIDER", "openai"),
            model=values.get(f"{prefix}MODEL", "gpt-5"),
            api_key=values.get(f"{prefix}API_KEY"),
            base_url=values.get(f"{prefix}BASE_URL"),
            temperature=float(values.get(f"{prefix}TEMPERATURE", "0")),
            timeout_seconds=float(
                values.get(f"{prefix}TIMEOUT_SECONDS", "30")
            ),
            minimum_confidence=float(
                values.get(f"{prefix}MIN_CONFIDENCE", "0.55")
            ),
        )


def create_langchain_chat_model(settings: LLMSettings) -> Any:
    if settings.provider not in {"openai", "openai_compatible"}:
        raise ValueError(f"Unsupported LLM provider: {settings.provider}")
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as exc:
        raise RuntimeError(
            "Install the optional LLM dependency with "
            "`pip install -e '.[llm]'`"
        ) from exc
    if not settings.api_key:
        raise ValueError("DATA_AGENT_LLM_API_KEY is required when LLM is enabled")
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
    if not settings.enabled:
        return RuleBasedIntentRouter()
    factory = model_factory or create_langchain_chat_model
    return LlmIntentRouter(
        factory(settings),
        minimum_confidence=settings.minimum_confidence,
    )
