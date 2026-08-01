"""Provider-neutral local embedding contracts and Ollama adapter."""

from dataclasses import dataclass
from math import ceil
from typing import Protocol

import httpx


class EmbeddingError(Exception):
    """Base controlled embedding failure."""


class EmbeddingConfigurationError(EmbeddingError):
    pass


class EmbeddingUnavailableError(EmbeddingError):
    pass


class EmbeddingModelError(EmbeddingError):
    pass


class EmbeddingResponseError(EmbeddingError):
    pass


@dataclass(frozen=True)
class EmbeddingIdentity:
    provider: str
    model: str
    revision: str
    dimension: int
    distance_metric: str = "cosine"
    normalization: str = "provider-defined"
    endpoint: str = ""
    maximum_input: str = "unknown"

    @property
    def stable_identity(self) -> str:
        return f"{self.provider}:{self.model}:{self.revision or 'unreported'}"


class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def health_check(self) -> EmbeddingIdentity: ...
    def get_model_identity(self) -> EmbeddingIdentity: ...
    def get_configured_identity(self) -> EmbeddingIdentity: ...


class OllamaEmbedder:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: float = 120,
        batch_size: int = 16,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not model.strip():
            raise EmbeddingConfigurationError("EMBEDDING_MODEL is not configured.")
        if isinstance(batch_size, bool) or not isinstance(batch_size, int):
            raise EmbeddingConfigurationError(
                "EMBEDDING_BATCH_SIZE must be a positive integer."
            )
        if batch_size <= 0:
            raise EmbeddingConfigurationError(
                "EMBEDDING_BATCH_SIZE must be a positive integer."
            )
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.transport = transport
        self._identity: EmbeddingIdentity | None = None

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts or any(not text.strip() for text in texts):
            raise EmbeddingConfigurationError("Embedding input must be non-empty.")
        vectors: list[list[float]] = []
        total_batches = ceil(len(texts) / self.batch_size)
        for offset in range(0, len(texts), self.batch_size):
            batch = texts[offset : offset + self.batch_size]
            batch_number = offset // self.batch_size + 1
            context = self._batch_context(
                batch_number, total_batches, offset, offset + len(batch) - 1
            )
            try:
                data = self._post({"model": self.model, "input": batch})
                raw = data.get("embeddings")
                if not isinstance(raw, list) or len(raw) != len(batch):
                    raise EmbeddingResponseError(
                        f"Embedding response count was invalid for {context}."
                    )
                batch_vectors = [self._validate_vector(vector) for vector in raw]
                dimensions = {len(vector) for vector in batch_vectors}
                if len(dimensions) != 1:
                    raise EmbeddingResponseError(
                        f"Embedding dimensions were inconsistent for {context}."
                    )
                self._remember_identity(dimensions.pop(), context=context)
            except EmbeddingError as exc:
                if context in str(exc):
                    raise
                message = str(exc).rstrip(".")
                raise type(exc)(f"{message} for {context}.") from exc
            vectors.extend(batch_vectors)
        if len(vectors) != len(texts):
            raise EmbeddingResponseError("Embedding output count was invalid.")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_documents([text])[0]

    def health_check(self) -> EmbeddingIdentity:
        self.embed_query("embedding provider health check")
        return self.get_model_identity()

    def get_model_identity(self) -> EmbeddingIdentity:
        if self._identity is None:
            raise EmbeddingConfigurationError(
                "Model identity is available after a successful embedding."
            )
        return self._identity

    def get_configured_identity(self) -> EmbeddingIdentity:
        return EmbeddingIdentity(
            provider="ollama",
            model=self.model,
            revision="unreported",
            dimension=self._identity.dimension if self._identity else 0,
            endpoint=self.base_url,
        )

    def _post(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            with httpx.Client(
                base_url=self.base_url,
                timeout=self.timeout_seconds,
                transport=self.transport,
                trust_env=False,
            ) as client:
                response = client.post("/api/embed", json=payload)
        except httpx.TimeoutException as exc:
            raise EmbeddingUnavailableError("Embedding request timed out.") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingUnavailableError(
                "Local embedding provider is unavailable."
            ) from exc
        if response.status_code == 404:
            raise EmbeddingModelError("Configured embedding model is unavailable.")
        if response.is_error:
            raise EmbeddingUnavailableError("Embedding provider returned an error.")
        try:
            data = response.json()
        except ValueError as exc:
            raise EmbeddingResponseError("Embedding response was not JSON.") from exc
        if not isinstance(data, dict):
            raise EmbeddingResponseError("Embedding response was malformed.")
        return data

    @staticmethod
    def _validate_vector(value: object) -> list[float]:
        if not isinstance(value, list) or not value:
            raise EmbeddingResponseError("Embedding vector was empty or malformed.")
        if any(
            not isinstance(item, int | float) or isinstance(item, bool)
            for item in value
        ):
            raise EmbeddingResponseError(
                "Embedding vector contained non-numeric values."
            )
        return [float(item) for item in value]

    def _remember_identity(self, dimension: int, *, context: str) -> None:
        identity = EmbeddingIdentity(
            provider="ollama",
            model=self.model,
            revision="unreported",
            dimension=dimension,
            endpoint=self.base_url,
        )
        if self._identity and self._identity.dimension != dimension:
            raise EmbeddingResponseError(
                f"Embedding dimension changed unexpectedly for {context}."
            )
        self._identity = identity

    @staticmethod
    def _batch_context(
        batch_number: int, total_batches: int, start: int, end: int
    ) -> str:
        return f"batch {batch_number}/{total_batches}, inputs {start}-{end}"
