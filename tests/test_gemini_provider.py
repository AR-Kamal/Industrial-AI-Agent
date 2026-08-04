from types import SimpleNamespace
from typing import Any
from unittest.mock import Mock, patch

import pytest
from google.genai import errors

from apps.ai_gateway.config import LLMConfig, get_llm_config
from apps.ai_gateway.errors import (
    EmptyResponseError,
    ModelNotInstalledError,
    ProviderAuthenticationError,
    ProviderConfigurationError,
    ProviderRateLimitError,
    ProviderSafetyError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from apps.ai_gateway.factory import get_llm_provider
from apps.ai_gateway.providers.gemini import GeminiProvider
from apps.ai_gateway.services import ChatMessage, TextGenerationRequest


def config() -> LLMConfig:
    return LLMConfig(
        provider="gemini",
        base_url="",
        api_key="",
        text_model="gemini-3.6-flash",
        timeout_seconds=12,
        temperature=0.1,
        max_tokens=700,
        structured_output=True,
        gemini_api_key="secret-test-key",
    )


class FakeClient:
    def __init__(self, result: Any = None, error: Exception | None = None) -> None:
        self.result = result
        self.error = error
        self.closed = False
        self.calls: list[dict[str, Any]] = []
        self.interactions = self

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.result

    def close(self) -> None:
        self.closed = True


def interaction(text: str = '{"status":"answered"}') -> Any:
    usage = SimpleNamespace(
        total_input_tokens=123, total_output_tokens=17, total_tokens=140
    )
    return SimpleNamespace(output_text=text, model="gemini-3.6-flash", usage=usage)


def request() -> TextGenerationRequest:
    return TextGenerationRequest(
        messages=(
            ChatMessage("system", "Ground only in evidence."),
            ChatMessage("user", "Question and [E1]."),
        ),
        temperature=0.9,
        max_tokens=321,
        response_schema={
            "type": "object",
            "properties": {"status": {"type": "string", "pattern": "answered"}},
            "required": ["status"],
            "additionalProperties": False,
            "allOf": [{"if": {}, "then": {}}],
        },
    )


def test_structured_generation_uses_interactions_api_without_sampling_or_storage() -> (
    None
):
    client = FakeClient(interaction())
    result = GeminiProvider(config(), client_factory=lambda: client).generate(request())

    call = client.calls[0]
    assert call["model"] == "gemini-3.6-flash"
    assert call["store"] is False
    assert call["system_instruction"] == "Ground only in evidence."
    assert call["input"] == [
        {"type": "text", "text": "[USER MESSAGE]\nQuestion and [E1]."}
    ]
    assert call["generation_config"] == {"max_output_tokens": 321}
    assert "temperature" not in call
    assert "tools" not in call
    schema = call["response_format"]["schema"]
    assert "additionalProperties" not in schema
    assert "allOf" not in schema
    assert "pattern" not in schema["properties"]["status"]
    assert client.closed is True
    assert result.total_tokens == 140
    assert result.input_tokens == 123


def test_health_check_is_minimal_and_reports_usage() -> None:
    client = FakeClient(interaction("OK"))
    health = GeminiProvider(config(), client_factory=lambda: client).health_check()
    assert client.calls[0]["input"] == "Reply with OK."
    assert client.calls[0]["store"] is False
    assert health.available is True
    assert health.total_tokens == 140
    assert client.closed is True


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError(), ProviderTimeoutError),
        (errors.ClientError(401, {}), ProviderAuthenticationError),
        (errors.ClientError(429, {}), ProviderRateLimitError),
        (errors.ClientError(404, {}), ModelNotInstalledError),
        (errors.ServerError(503, {}), ProviderUnavailableError),
    ],
)
def test_provider_errors_are_normalized(
    error: Exception, expected: type[Exception]
) -> None:
    client = FakeClient(error=error)
    with pytest.raises(expected):
        GeminiProvider(config(), client_factory=lambda: client).generate(request())
    assert client.closed is True


def test_empty_response_is_rejected() -> None:
    with pytest.raises(EmptyResponseError):
        GeminiProvider(
            config(), client_factory=lambda: FakeClient(interaction("  "))
        ).generate(request())


def test_detectable_provider_refusal_is_mapped_safely() -> None:
    refused = SimpleNamespace(output_text=None, status="refused", outputs=[])
    with pytest.raises(ProviderSafetyError):
        GeminiProvider(config(), client_factory=lambda: FakeClient(refused)).generate(
            request()
        )


def test_missing_usage_is_tolerated_and_key_is_not_represented() -> None:
    result = GeminiProvider(
        config(),
        client_factory=lambda: FakeClient(
            SimpleNamespace(output_text="{}", model=None, usage=None)
        ),
    ).generate(request())
    assert result.total_tokens is None
    assert "secret-test-key" not in repr(config())


@pytest.mark.django_db
def test_gemini_requires_dedicated_key(settings: Any) -> None:
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = ""
    with pytest.raises(ProviderConfigurationError):
        get_llm_config()


@pytest.mark.django_db
def test_factory_selects_gemini_without_validating_ollama_url(settings: Any) -> None:
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "test-key"
    settings.LLM_TEXT_MODEL = "gemini-3.6-flash"
    settings.LLM_BASE_URL = "unused"
    assert isinstance(get_llm_provider(), GeminiProvider)


@pytest.mark.django_db
def test_gemini_selection_never_constructs_ollama_fallback(settings: Any) -> None:
    settings.LLM_PROVIDER = "gemini"
    settings.GEMINI_API_KEY = "test-key"
    settings.LLM_TEXT_MODEL = "gemini-3.6-flash"
    gemini = Mock(spec=GeminiProvider)
    with (
        patch(
            "apps.ai_gateway.factory.GeminiProvider", return_value=gemini
        ) as gemini_class,
        patch("apps.ai_gateway.factory.OllamaProvider") as ollama_class,
    ):
        assert get_llm_provider() is gemini
    gemini_class.assert_called_once()
    ollama_class.assert_not_called()


@pytest.mark.django_db
def test_default_selection_constructs_only_ollama(settings: Any) -> None:
    settings.LLM_PROVIDER = "ollama"
    settings.GEMINI_API_KEY = ""
    ollama = Mock()
    with (
        patch("apps.ai_gateway.factory.OllamaProvider", return_value=ollama),
        patch("apps.ai_gateway.factory.GeminiProvider") as gemini_class,
    ):
        assert get_llm_provider() is ollama
    gemini_class.assert_not_called()


@pytest.mark.django_db
def test_ollama_does_not_require_gemini_key(settings: Any) -> None:
    settings.LLM_PROVIDER = "ollama"
    settings.GEMINI_API_KEY = ""
    assert get_llm_config().provider == "ollama"


@pytest.mark.django_db
@pytest.mark.parametrize("provider", ["unknown", "gemini"])
def test_invalid_provider_or_blank_gemini_model_is_rejected(
    settings: Any, provider: str
) -> None:
    settings.LLM_PROVIDER = provider
    settings.GEMINI_API_KEY = "test-key"
    settings.LLM_TEXT_MODEL = "" if provider == "gemini" else "model"
    with pytest.raises(ProviderConfigurationError):
        get_llm_config()
