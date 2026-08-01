"""Application-facing text gateway."""

from collections.abc import Sequence
from typing import Any

from .config import get_llm_config
from .factory import get_llm_provider
from .services import (
    ChatMessage,
    LLMProvider,
    ProviderHealth,
    TextGenerationRequest,
    TextGenerationResult,
)


class TextGateway:
    """Apply configured generation controls to a replaceable provider."""

    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.config = get_llm_config()
        self.provider = provider or get_llm_provider()

    def generate(self, messages: Sequence[ChatMessage]) -> TextGenerationResult:
        request = TextGenerationRequest(
            messages=tuple(messages),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )
        return self.provider.generate(request)

    def generate_structured(
        self, messages: Sequence[ChatMessage], schema: dict[str, Any]
    ) -> TextGenerationResult:
        """Generate one non-streaming response constrained by a JSON schema."""
        request = TextGenerationRequest(
            messages=tuple(messages),
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
            response_schema=schema if self.config.structured_output else None,
        )
        return self.provider.generate(request)

    def health_check(self) -> ProviderHealth:
        return self.provider.health_check()

    def get_model_identity(self) -> str:
        return self.provider.get_model_identity()


def get_text_gateway() -> TextGateway:
    return TextGateway()
