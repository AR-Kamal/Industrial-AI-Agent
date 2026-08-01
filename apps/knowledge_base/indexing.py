"""Versioned vector indexing with Django-authoritative eligibility."""

import hashlib
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from django.db import transaction
from django.db.models import Exists, OuterRef, QuerySet
from django.utils import timezone
from qdrant_client import QdrantClient, models

from apps.ai_gateway.embeddings import Embedder, EmbeddingIdentity

from .models import (
    ChunkEmbeddingRecord,
    ChunkReplacementCorrection,
    ChunkSplitCorrection,
    DocumentChunk,
    KnowledgeDocument,
    VectorIndexVersion,
)

POINT_NAMESPACE = uuid.UUID("33408285-67d3-4b35-a85b-2b9659238ae0")


def eligible_chunks() -> QuerySet[DocumentChunk]:
    """Return the single authoritative retrieval-eligible chunk set."""
    stale_split = ChunkSplitCorrection.objects.filter(
        document_version_id=OuterRef("document_version_id"),
        status=ChunkSplitCorrection.Status.STALE,
    )
    stale_replacement = ChunkReplacementCorrection.objects.filter(
        replacement_child_id=OuterRef("pk"),
        status=ChunkReplacementCorrection.Status.STALE,
    )
    return (
        DocumentChunk.objects.annotate(
            has_stale_split=Exists(stale_split),
            has_stale_replacement=Exists(stale_replacement),
        )
        .filter(
            review_status=DocumentChunk.ReviewStatus.APPROVED,
            is_current_generation=True,
            retrieval_enabled=True,
            document__approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
            document__lifecycle_status=KnowledgeDocument.LifecycleStatus.PROCESSED,
            document_version__processed_at__isnull=False,
            has_stale_split=False,
            has_stale_replacement=False,
        )
        .exclude(content__regex=r"^\s*$")
        .exclude(content_hash="")
        .select_related("document", "document_version")
    )


def normalize_embedding_input(content: str) -> str:
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    return re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", normalized)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def point_id(index_id: uuid.UUID, chunk_id: str) -> uuid.UUID:
    return uuid.uuid5(POINT_NAMESPACE, f"{index_id}:{chunk_id}")


def corpus_fingerprint(chunks: Iterable[DocumentChunk]) -> str:
    material = "\n".join(
        f"{chunk.chunk_id}:{chunk.content_hash}"
        for chunk in sorted(chunks, key=lambda c: c.chunk_id)
    )
    return sha256_text(material)


@dataclass(frozen=True)
class VectorCandidate:
    point_id: str
    score: float
    payload: dict[str, object]


class QdrantLocalStore:
    """Restricted Qdrant Local Mode adapter."""

    def __init__(self, path: Path | str) -> None:
        self.client = QdrantClient(path=str(path))

    def __enter__(self) -> "QdrantLocalStore":
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def create_collection(self, name: str, dimension: int, metric: str) -> None:
        distance = {"cosine": models.Distance.COSINE}.get(metric.lower())
        if distance is None:
            raise ValueError("Only cosine distance is currently supported.")
        self.client.create_collection(
            collection_name=name,
            vectors_config=models.VectorParams(size=dimension, distance=distance),
        )

    def upsert(
        self, name: str, points: list[tuple[uuid.UUID, list[float], dict[str, object]]]
    ) -> None:
        self.client.upsert(
            collection_name=name,
            points=[
                models.PointStruct(id=str(identifier), vector=vector, payload=payload)
                for identifier, vector, payload in points
            ],
            wait=True,
        )

    def search(
        self, name: str, vector: list[float], limit: int
    ) -> list[VectorCandidate]:
        result = self.client.query_points(
            collection_name=name, query=vector, limit=limit, with_payload=True
        ).points
        return [
            VectorCandidate(str(item.id), float(item.score), dict(item.payload or {}))
            for item in result
        ]

    def count(self, name: str) -> int:
        return int(self.client.count(name, exact=True).count)

    def delete_collection(self, name: str) -> None:
        self.client.delete_collection(name)


def build_index(
    embedder: Embedder,
    store: QdrantLocalStore,
    *,
    document_id: str | None = None,
) -> VectorIndexVersion:
    chunks = list(
        eligible_chunks().filter(document_id=document_id)
        if document_id
        else eligible_chunks()
    )
    if not chunks:
        raise ValueError("No eligible chunks were found.")
    inputs = [normalize_embedding_input(chunk.content) for chunk in chunks]
    fingerprint = corpus_fingerprint(chunks)
    configured_identity = embedder.get_configured_identity()
    index = VectorIndexVersion.objects.create(
        collection_name=f"kb_{fingerprint[:12]}_{uuid.uuid4().hex[:8]}",
        provider=configured_identity.provider,
        model_name=configured_identity.model,
        model_identity=configured_identity.stable_identity,
        vector_dimension=configured_identity.dimension,
        distance_metric=configured_identity.distance_metric,
        normalization=configured_identity.normalization,
        corpus_fingerprint=fingerprint,
        eligible_chunk_count=len(chunks),
        configuration={"document_id": document_id or "all"},
    )
    try:
        vectors = embedder.embed_documents(inputs)
        identity: EmbeddingIdentity = embedder.get_model_identity()
        index.vector_dimension = identity.dimension
        index.model_identity = identity.stable_identity
        index.distance_metric = identity.distance_metric
        index.normalization = identity.normalization
        index.save(
            update_fields=[
                "vector_dimension",
                "model_identity",
                "distance_metric",
                "normalization",
            ]
        )
        store.create_collection(
            index.collection_name, identity.dimension, identity.distance_metric
        )
        points: list[tuple[uuid.UUID, list[float], dict[str, object]]] = []
        records = []
        for chunk, text, vector in zip(chunks, inputs, vectors, strict=True):
            identifier = point_id(index.id, chunk.chunk_id)
            payload: dict[str, object] = {
                "chunk_id": chunk.chunk_id,
                "source_content_hash": chunk.content_hash,
                "embedding_input_hash": sha256_text(text),
                "document_id": chunk.document_id,
                "document_version_id": chunk.document_version_id,
            }
            points.append((identifier, vector, payload))
            records.append(
                ChunkEmbeddingRecord(
                    index_version=index,
                    chunk=chunk,
                    vector_point_id=identifier,
                    source_content_hash=chunk.content_hash,
                    embedding_input_hash=sha256_text(text),
                    model_identity=identity.stable_identity,
                    vector_dimension=identity.dimension,
                )
            )
        store.upsert(index.collection_name, points)
        if store.count(index.collection_name) != len(chunks):
            raise ValueError("Vector count did not match the eligible corpus.")
        with transaction.atomic():
            index.status = VectorIndexVersion.Status.VALIDATING
            index.indexed_chunk_count = len(chunks)
            index.save(update_fields=["status", "indexed_chunk_count"])
            ChunkEmbeddingRecord.objects.bulk_create(records)
            VectorIndexVersion.objects.filter(
                status=VectorIndexVersion.Status.ACTIVE
            ).update(
                status=VectorIndexVersion.Status.RETIRED, retired_at=timezone.now()
            )
            index.status = VectorIndexVersion.Status.ACTIVE
            index.activated_at = timezone.now()
            index.save(update_fields=["status", "activated_at"])
    except Exception as exc:
        index.status = VectorIndexVersion.Status.FAILED
        index.failure_detail = type(exc).__name__
        index.save(update_fields=["status", "failure_detail"])
        raise
    return index
