"""Google Gemini adapter using the official Interactions API client."""

from collections.abc import Callable, Mapping
from time import perf_counter
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from apps.ai_gateway.config import LLMConfig
from apps.ai_gateway.errors import (
    EmptyResponseError,
    ModelNotInstalledError,
    ProviderAuthenticationError,
    ProviderPermissionError,
    ProviderRateLimitError,
    ProviderSafetyError,
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

ClientFactory = Callable[[], Any]


class GeminiProvider(LLMProvider):
    """Generate non-streaming text through Gemini without provider fallback."""

    def __init__(
        self, config: LLMConfig, *, client_factory: ClientFactory | None = None
    ) -> None:
        self.config = config
        self._client_factory = client_factory or self._new_client

    def _new_client(self) -> Any:
        return genai.Client(
            api_key=self.config.gemini_api_key,
            http_options=types.HttpOptions(
                timeout=int(self.config.timeout_seconds * 1000),
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )

    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        system, interaction_input = self._map_messages(request)
        body: dict[str, Any] = {
            "model": self.config.text_model,
            "input": interaction_input,
            "store": False,
            "generation_config": {"max_output_tokens": request.max_tokens},
        }
        if system:
            body["system_instruction"] = system
        if request.response_schema is not None:
            body["response_format"] = {
                "type": "text",
                "mime_type": "application/json",
                "schema": _supported_schema(request.response_schema),
            }

        started = perf_counter()
        interaction = self._create_interaction(body)
        duration_ms = (perf_counter() - started) * 1000
        text = getattr(interaction, "output_text", None)
        if not isinstance(text, str) or not text.strip():
            if _is_refusal(interaction):
                raise ProviderSafetyError("The provider declined the request.")
            raise EmptyResponseError("The provider returned an empty response.")
        usage = getattr(interaction, "usage", None)
        return TextGenerationResult(
            text=text.strip(),
            provider=self.config.provider,
            model=str(getattr(interaction, "model", None) or self.config.text_model),
            duration_ms=duration_ms,
            input_tokens=_usage_value(usage, "total_input_tokens"),
            output_tokens=_usage_value(usage, "total_output_tokens"),
            total_tokens=_usage_value(usage, "total_tokens"),
        )

    def health_check(self) -> ProviderHealth:
        started = perf_counter()
        interaction = self._create_interaction(
            {
                "model": self.config.text_model,
                "input": "Reply with OK.",
                "store": False,
                "generation_config": {"max_output_tokens": 8},
            }
        )
        usage = getattr(interaction, "usage", None)
        return ProviderHealth(
            provider=self.config.provider,
            model=str(getattr(interaction, "model", None) or self.config.text_model),
            available=True,
            detail="Provider and configured text model are available.",
            duration_ms=(perf_counter() - started) * 1000,
            input_tokens=_usage_value(usage, "total_input_tokens"),
            output_tokens=_usage_value(usage, "total_output_tokens"),
            total_tokens=_usage_value(usage, "total_tokens"),
        )

    def get_model_identity(self) -> str:
        return f"{self.config.provider}:{self.config.text_model}"

    def _create_interaction(self, body: dict[str, Any]) -> Any:
        client = self._client_factory()
        try:
            return client.interactions.create(**body)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProviderTimeoutError("The generation request timed out.") from exc
        except errors.APIError as exc:
            self._raise_api_error(exc)
        except (httpx.ConnectError, OSError) as exc:
            raise ProviderUnavailableError(
                "The generation provider is unavailable."
            ) from exc
        except Exception as exc:
            raise UnexpectedProviderError("The generation request failed.") from exc
        finally:
            close = getattr(client, "close", None)
            if callable(close):
                close()

    @staticmethod
    def _raise_api_error(exc: errors.APIError) -> None:
        status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
        if status == 401:
            raise ProviderAuthenticationError(
                "The generation provider rejected authentication."
            ) from exc
        if status == 403:
            raise ProviderPermissionError(
                "The generation provider rejected the request."
            ) from exc
        if status == 404:
            raise ModelNotInstalledError(
                "The configured model is unavailable."
            ) from exc
        if status == 429:
            raise ProviderRateLimitError(
                "The generation provider rate limit was reached."
            ) from exc
        if isinstance(status, int) and status >= 500:
            raise ProviderUnavailableError(
                "The generation provider is unavailable."
            ) from exc
        raise UnexpectedProviderError(
            "The generation provider returned an error."
        ) from exc

    @staticmethod
    def _map_messages(
        request: TextGenerationRequest,
    ) -> tuple[str, list[dict[str, Any]]]:
        system_parts = [m.content for m in request.messages if m.role == "system"]
        inputs = [
            {"type": "text", "text": f"[{m.role.upper()} MESSAGE]\n{m.content}"}
            for m in request.messages
            if m.role != "system"
        ]
        return "\n\n".join(system_parts), inputs


def _supported_schema(value: Any) -> Any:
    """Return the conservative JSON Schema subset accepted by Gemini."""
    if isinstance(value, list):
        return [_supported_schema(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    allowed = {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "description",
        "title",
        "minimum",
        "maximum",
        "minItems",
        "maxItems",
        "minLength",
        "maxLength",
    }
    result: dict[str, Any] = {}
    for key, item in value.items():
        if key not in allowed:
            continue
        if key == "properties" and isinstance(item, Mapping):
            result[key] = {
                property_name: _supported_schema(property_schema)
                for property_name, property_schema in item.items()
            }
        else:
            result[key] = _supported_schema(item)
    return result


def _usage_value(usage: Any, name: str) -> int | None:
    value = getattr(usage, name, None)
    return value if isinstance(value, int) and value >= 0 else None


def _is_refusal(interaction: Any) -> bool:
    status = getattr(interaction, "status", None)
    if isinstance(status, str) and status.lower() in {"blocked", "refused"}:
        return True
    outputs = getattr(interaction, "outputs", None)
    if not isinstance(outputs, list):
        return False
    return any(
        str(getattr(output, "type", "")).lower() in {"blocked", "refusal", "refused"}
        for output in outputs
    )
