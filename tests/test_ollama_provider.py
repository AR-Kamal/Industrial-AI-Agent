import json

import httpx
import pytest

from apps.ai_gateway.config import LLMConfig
from apps.ai_gateway.errors import (
    EmptyResponseError,
    MalformedResponseError,
    ModelNotInstalledError,
    ProviderConfigurationError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnexpectedProviderError,
)
from apps.ai_gateway.providers.ollama import OllamaProvider
from apps.ai_gateway.services import ChatMessage, TextGenerationRequest


def make_config() -> LLMConfig:
    return LLMConfig(
        provider="ollama",
        base_url="http://127.0.0.1:11434/v1",
        api_key="placeholder-secret",
        text_model="test-model",
        timeout_seconds=2.0,
        temperature=0.1,
        max_tokens=256,
    )


def make_request() -> TextGenerationRequest:
    return TextGenerationRequest(
        messages=(ChatMessage(role="user", content="Explain alarm SRVO-001."),),
        temperature=0.2,
        max_tokens=300,
    )


def test_generate_uses_openai_compatible_schema() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer placeholder-secret"
        assert payload["model"] == "test-model"
        assert payload["temperature"] == 0.2
        assert payload["max_tokens"] == 300
        assert payload["stream"] is False
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": "Safe training answer."}}]},
        )

    provider = OllamaProvider(make_config(), transport=httpx.MockTransport(handler))

    result = provider.generate(make_request())

    assert result.text == "Safe training answer."
    assert result.provider == "ollama"
    assert result.model == "test-model"


def test_health_check_confirms_configured_model() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"data": [{"id": "test-model"}, {"id": "another-model"}]},
        )
    )

    health = OllamaProvider(make_config(), transport=transport).health_check()

    assert health.available is True
    assert health.model == "test-model"


def test_health_check_reports_missing_model() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"data": [{"id": "other-model"}]})
    )

    with pytest.raises(ModelNotInstalledError):
        OllamaProvider(make_config(), transport=transport).health_check()


def test_provider_unavailable_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    provider = OllamaProvider(make_config(), transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderUnavailableError):
        provider.generate(make_request())


def test_timeout_is_normalized() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    provider = OllamaProvider(make_config(), transport=httpx.MockTransport(handler))

    with pytest.raises(ProviderTimeoutError):
        provider.generate(make_request())


def test_model_not_installed_is_normalized() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(404, json={"error": "model not found"})
    )

    with pytest.raises(ModelNotInstalledError):
        OllamaProvider(make_config(), transport=transport).generate(make_request())


@pytest.mark.parametrize(
    ("response", "expected_error"),
    [
        (
            httpx.Response(
                200,
                json={"choices": [{"message": {"content": "   "}}]},
            ),
            EmptyResponseError,
        ),
        (httpx.Response(200, content=b"not-json"), MalformedResponseError),
        (httpx.Response(200, json={"choices": []}), MalformedResponseError),
        (httpx.Response(500, json={"error": "internal"}), UnexpectedProviderError),
    ],
)
def test_bad_provider_responses_are_normalized(
    response: httpx.Response,
    expected_error: type[Exception],
) -> None:
    provider = OllamaProvider(
        make_config(),
        transport=httpx.MockTransport(lambda request: response),
    )

    with pytest.raises(expected_error):
        provider.generate(make_request())


@pytest.mark.django_db
def test_external_ollama_url_is_rejected(settings) -> None:
    from apps.ai_gateway.config import get_llm_config

    settings.LLM_BASE_URL = "https://external.example/v1"

    with pytest.raises(ProviderConfigurationError):
        get_llm_config()
