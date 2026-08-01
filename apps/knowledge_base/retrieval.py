"""Dense retrieval with mandatory Django-side revalidation."""

from dataclasses import dataclass

from apps.ai_gateway.embeddings import Embedder

from .indexing import QdrantLocalStore, VectorCandidate, eligible_chunks
from .models import DocumentChunk, VectorIndexVersion

SAFETY_RANKING_BONUS_FACTOR = 0.04
SAFETY_RANKING_MAX_BONUS = 0.02


@dataclass(frozen=True)
class RetrievedChunk:
    rank: int
    score: float
    semantic_score: float
    ranking_score: float
    safety_priority_applied: float
    ranking_reason: str
    retrieval_mode: str
    chunk_id: str
    document_id: str
    document_version_id: str
    chapter: str
    section: str
    page_start: int | None
    page_end: int | None
    contains_warning: bool
    contains_caution: bool
    source_content_hash: str
    index_version_id: str
    content: str


@dataclass(frozen=True)
class RankedCandidate:
    candidate: VectorCandidate
    chunk: DocumentChunk
    semantic_score: float
    ranking_score: float
    safety_priority_applied: float
    ranking_reason: str


def _rank_candidates(
    valid: list[tuple[VectorCandidate, DocumentChunk]], *, safety_first: bool
) -> list[RankedCandidate]:
    ranked: list[RankedCandidate] = []
    for candidate, chunk in valid:
        semantic_score = float(candidate.score)
        is_safety = bool(chunk.contains_warning or chunk.contains_caution)
        bonus = (
            min(
                SAFETY_RANKING_MAX_BONUS,
                max(0.0, semantic_score) * SAFETY_RANKING_BONUS_FACTOR,
            )
            if safety_first and is_safety
            else 0.0
        )
        reason = (
            "semantic_similarity_plus_bounded_safety_priority"
            if bonus
            else "semantic_similarity"
        )
        ranked.append(
            RankedCandidate(
                candidate=candidate,
                chunk=chunk,
                semantic_score=semantic_score,
                ranking_score=semantic_score + bonus,
                safety_priority_applied=bonus,
                ranking_reason=reason,
            )
        )
    return sorted(
        ranked,
        key=lambda item: (
            -item.ranking_score,
            -item.semantic_score,
            str(item.chunk.chunk_id),
        ),
    )


def retrieve(
    query: str,
    embedder: Embedder,
    store: QdrantLocalStore,
    *,
    top_k: int = 5,
    max_top_k: int = 10,
    minimum_score: float | None = None,
    safety_first: bool = False,
    document_id: str | None = None,
) -> list[RetrievedChunk]:
    if not query.strip():
        raise ValueError("Query must not be empty.")
    if top_k < 1 or top_k > max_top_k:
        raise ValueError(f"top_k must be between 1 and {max_top_k}.")
    index = VectorIndexVersion.objects.get(status=VectorIndexVersion.Status.ACTIVE)
    candidates = store.search(
        index.collection_name, embedder.embed_query(query), top_k * 3
    )
    chunk_ids = [str(item.payload.get("chunk_id", "")) for item in candidates]
    queryset = eligible_chunks().filter(chunk_id__in=chunk_ids)
    if document_id:
        queryset = queryset.filter(document_id=document_id)
    current = {chunk.chunk_id: chunk for chunk in queryset}
    valid = []
    seen: set[str] = set()
    for candidate in candidates:
        chunk_id = str(candidate.payload.get("chunk_id", ""))
        chunk = current.get(chunk_id)
        if (
            chunk is None
            or chunk_id in seen
            or candidate.payload.get("source_content_hash") != chunk.content_hash
            or (minimum_score is not None and candidate.score < minimum_score)
        ):
            continue
        seen.add(chunk_id)
        valid.append((candidate, chunk))
    ranked = _rank_candidates(valid, safety_first=safety_first)
    return [
        RetrievedChunk(
            rank=rank,
            score=item.semantic_score,
            semantic_score=item.semantic_score,
            ranking_score=item.ranking_score,
            safety_priority_applied=item.safety_priority_applied,
            ranking_reason=item.ranking_reason,
            retrieval_mode="safety_first" if safety_first else "dense",
            chunk_id=item.chunk.chunk_id,
            document_id=item.chunk.document_id,
            document_version_id=item.chunk.document_version_id,
            chapter=item.chunk.chapter,
            section=item.chunk.section,
            page_start=item.chunk.page_start,
            page_end=item.chunk.page_end,
            contains_warning=item.chunk.contains_warning,
            contains_caution=item.chunk.contains_caution,
            source_content_hash=item.chunk.content_hash,
            index_version_id=str(index.id),
            content=item.chunk.content,
        )
        for rank, item in enumerate(ranked[:top_k], start=1)
    ]
