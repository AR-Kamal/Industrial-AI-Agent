"""Validated construction of Milestone 4 runtime adapters."""

from pathlib import Path

from django.conf import settings

from apps.ai_gateway.embeddings import OllamaEmbedder

from .indexing import QdrantLocalStore


def embedding_provider() -> OllamaEmbedder:
    if settings.EMBEDDING_PROVIDER != "ollama":
        raise ValueError("Only the configured local Ollama provider is supported.")
    return OllamaEmbedder(
        settings.EMBEDDING_BASE_URL,
        settings.EMBEDDING_MODEL,
        settings.EMBEDDING_TIMEOUT_SECONDS,
        settings.EMBEDDING_BATCH_SIZE,
    )


def vector_store() -> QdrantLocalStore:
    if settings.VECTOR_STORE_PROVIDER != "qdrant" or settings.QDRANT_MODE != "local":
        raise ValueError("Milestone 4 requires Qdrant Local Mode.")
    configured = Path(settings.QDRANT_PATH)
    path = configured if configured.is_absolute() else settings.BASE_DIR / configured
    return QdrantLocalStore(path.resolve())
