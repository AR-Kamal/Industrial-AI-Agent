"""Validated LLM gateway configuration."""

from dataclasses import dataclass
from urllib.parse import urlparse

from django.conf import settings

from .errors import ProviderConfigurationError

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass(frozen=True)
class LLMConfig:
    provider: str
    base_url: str
    api_key: str
    text_model: str
    timeout_seconds: float
    temperature: float
    max_tokens: int


def get_llm_config() -> LLMConfig:
    config = LLMConfig(
        provider=str(settings.LLM_PROVIDER).strip().lower(),
        base_url=str(settings.LLM_BASE_URL).strip().rstrip("/"),
        api_key=str(settings.LLM_API_KEY),
        text_model=str(settings.LLM_TEXT_MODEL).strip(),
        timeout_seconds=float(settings.LLM_TIMEOUT_SECONDS),
        temperature=float(settings.LLM_TEMPERATURE),
        max_tokens=int(settings.LLM_MAX_TOKENS),
    )
    _validate(config)
    return config


def _validate(config: LLMConfig) -> None:
    if config.provider != "ollama":
        raise ProviderConfigurationError("Unsupported LLM provider.")
    if not config.text_model:
        raise ProviderConfigurationError("A text model must be configured.")
    if config.timeout_seconds <= 0:
        raise ProviderConfigurationError("The timeout must be greater than zero.")
    if not 0 <= config.temperature <= 2:
        raise ProviderConfigurationError("Temperature must be between 0 and 2.")
    if config.max_tokens <= 0:
        raise ProviderConfigurationError("Maximum tokens must be greater than zero.")

    parsed = urlparse(config.base_url)
    if (
        parsed.scheme != "http"
        or parsed.hostname not in LOOPBACK_HOSTS
        or parsed.query
        or parsed.fragment
    ):
        raise ProviderConfigurationError(
            "The Ollama base URL must be a local HTTP loopback address."
        )
    if not parsed.path.rstrip("/").endswith("/v1"):
        raise ProviderConfigurationError(
            "The Ollama base URL must end with the OpenAI-compatible /v1 path."
        )
