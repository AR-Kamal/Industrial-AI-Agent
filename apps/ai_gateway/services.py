"""Provider-neutral AI service contracts."""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class TextGenerationRequest:
    messages: tuple[ChatMessage, ...]
    temperature: float
    max_tokens: int
    response_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class TextGenerationResult:
    text: str
    provider: str
    model: str
    duration_ms: float = 0.0


@dataclass(frozen=True)
class ProviderHealth:
    provider: str
    model: str
    available: bool
    detail: str


class LLMProvider(Protocol):
    def generate(self, request: TextGenerationRequest) -> TextGenerationResult:
        """Generate text through a server-side provider adapter."""

        ...

    def health_check(self) -> ProviderHealth:
        """Verify that the provider and configured model are available."""

        ...

    def get_model_identity(self) -> str:
        """Return the configured provider/model identity without a network call."""

        ...


class EmbeddingProvider(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Create vectors through a future embedding adapter."""

        ...


@dataclass(frozen=True)
class VisionRequest:
    image_bytes: bytes
    media_type: str
    prompt: str


@dataclass(frozen=True)
class VisionResult:
    observations: tuple[str, ...]
    provider: str
    model: str


class VisionProvider(Protocol):
    def analyze(self, request: VisionRequest) -> VisionResult:
        """Analyze an image through a future server-side provider adapter."""

        ...
