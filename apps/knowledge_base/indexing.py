"""Provider-neutral future indexing contracts.

Milestone 3 deliberately supplies no implementations.
"""

from collections.abc import Mapping, Sequence
from typing import Protocol


class EmbeddingGenerator(Protocol):
    def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        """Return document vectors from a future embedding provider."""

        ...


class VectorStore(Protocol):
    def upsert(
        self,
        ids: Sequence[str],
        vectors: Sequence[Sequence[float]],
        metadata: Sequence[Mapping[str, object]],
    ) -> None:
        """Store vectors through a future vector backend."""

        ...


class DocumentIndexer(Protocol):
    def index_document(self, document_id: str) -> None:
        """Embed and index approved chunks in a future milestone."""

        ...
