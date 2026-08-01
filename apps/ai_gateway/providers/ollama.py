"""Ollama adapter for its local OpenAI-compatible API."""

from collections.abc import Mapping
from time import perf_counter
from typing import Any

import httpx

from apps.ai_gateway.config import LLMConfig
from apps.ai_gateway.errors import (
    EmptyResponseError,
    MalformedResponseError,
    ModelNotInstalledError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnexpectedProviderError,
)
from apps.ai_gateway.services import (
    LLMProvider,
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResult,
)


class OllamaProvider(LLMProvider):
    """Call a local Ollama process without exposing it to the browser."""

    def __init__(
        self,
        config: LLMConfig,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self._transport = transport

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        payload = {
            "model": self.config.text_model,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in request.messages
            ],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "stream": False,
        }
        if request.response_schema is not None:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "grounded_answer",
                    "strict": True,
                    "schema": request.response_schema,
                },
            }
        started = perf_counter()
        response = self._request("POST", "/chat/completions", json=payload)
        data = self._response_json(response)
        text = self._extract_text(data)
        return TextGenerationResult(
            text=text,
            provider=self.config.provider,
            model=self.config.text_model,
            duration_ms=(perf_counter() - started) * 1000,
        )

    def get_model_identity(self) -> str:
        return f"{self.config.provider}:{self.config.text_model}"

    def health_check(self) -> ProviderHealth:
        response = self._request("GET", "/models")
        data = self._response_json(response)
        models = data.get("data")
        if not isinstance(models, list):
            raise MalformedResponseError("Provider model list was malformed.")

        model_ids = {
            item.get("id")
            for item in models
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        }
        if self.config.text_model not in model_ids:
            raise ModelNotInstalledError("The configured model is not installed.")
        return ProviderHealth(
            provider=self.config.provider,
            model=self.config.text_model,
            available=True,
            detail="Provider and configured text model are available.",
        )

    def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self.config.api_key}"}
        try:
            with httpx.Client(
                base_url=self.config.base_url,
                headers=headers,
                timeout=self.config.timeout_seconds,
                transport=self._transport,
                trust_env=False,
            ) as client:
                response = client.request(method, path, json=json)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError("The local model request timed out.") from exc
        except httpx.ConnectError as exc:
            raise ProviderUnavailableError(
                "The local model service is unavailable."
            ) from exc
        except httpx.HTTPError as exc:
            raise UnexpectedProviderError("The local model request failed.") from exc

        if response.status_code == 404:
            raise ModelNotInstalledError("The configured model is not installed.")
        if response.is_error:
            raise UnexpectedProviderError("The local model returned an error.")
        return response

    @staticmethod
    def _response_json(response: httpx.Response) -> dict[str, Any]:
        try:
            data = response.json()
        except ValueError as exc:
            raise MalformedResponseError("The provider response was not JSON.") from exc
        if not isinstance(data, dict):
            raise MalformedResponseError("The provider response was malformed.")
        return data

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise MalformedResponseError("The provider response had no choices.")
        first_choice = choices[0]
        if not isinstance(first_choice, dict):
            raise MalformedResponseError("The provider choice was malformed.")
        message = first_choice.get("message")
        if not isinstance(message, dict):
            raise MalformedResponseError("The provider message was malformed.")
        content = message.get("content")
        if not isinstance(content, str):
            raise MalformedResponseError("The provider content was malformed.")
        content = content.strip()
        if not content:
            raise EmptyResponseError("The provider returned an empty response.")
        return content
