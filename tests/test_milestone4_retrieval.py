import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import Mock

import httpx
import pytest
from django.test import override_settings

from apps.ai_gateway.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingResponseError,
    EmbeddingUnavailableError,
    OllamaEmbedder,
)
from apps.knowledge_base.indexing import (
    QdrantLocalStore,
    VectorCandidate,
    build_index,
    normalize_embedding_input,
    point_id,
    sha256_text,
)
from apps.knowledge_base.models import DocumentChunk, VectorIndexVersion
from apps.knowledge_base.retrieval import _rank_candidates, retrieve
from apps.knowledge_base.runtime import embedding_provider


def mock_embedder(payload: object) -> OllamaEmbedder:
    return OllamaEmbedder(
        "http://127.0.0.1:11434",
        "test-embed",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(200, json=payload)
        ),
    )


def test_embedding_single_and_model_identity() -> None:
    provider = mock_embedder({"embeddings": [[0.1, 0.2, 0.3]]})
    assert provider.embed_query("SRVO-199") == [0.1, 0.2, 0.3]
    identity = provider.get_model_identity()
    assert identity.model == "test-embed"
    assert identity.dimension == 3


def test_embedding_batch_and_batch_length_validation() -> None:
    provider = mock_embedder({"embeddings": [[1, 2], [3, 4]]})
    assert provider.embed_documents(["T1", "T2"]) == [[1.0, 2.0], [3.0, 4.0]]
    with pytest.raises(EmbeddingResponseError):
        mock_embedder({"embeddings": [[1, 2]]}).embed_documents(["T1", "T2"])


@override_settings(EMBEDDING_BATCH_SIZE=8, EMBEDDING_MODEL="configured-model")
def test_configured_batch_size_reaches_ollama_embedder() -> None:
    assert embedding_provider().batch_size == 8


def test_101_inputs_are_sent_as_seven_ordered_batches() -> None:
    request_sizes: list[int] = []
    received: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        request_sizes.append(len(inputs))
        received.extend(inputs)
        return httpx.Response(
            200,
            json={"embeddings": [[float(value), 0.0] for value in inputs]},
        )

    texts = [str(index) for index in range(101)]
    provider = OllamaEmbedder(
        "http://127.0.0.1:11434",
        "test-embed",
        batch_size=16,
        transport=httpx.MockTransport(handler),
    )
    vectors = provider.embed_documents(texts)
    assert request_sizes == [16, 16, 16, 16, 16, 16, 5]
    assert received == texts
    assert [vector[0] for vector in vectors] == [float(text) for text in texts]


def test_batch_size_eight_is_honored() -> None:
    request_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        request_sizes.append(len(inputs))
        return httpx.Response(200, json={"embeddings": [[1.0] for _ in inputs]})

    provider = OllamaEmbedder(
        "http://127.0.0.1:11434",
        "test-embed",
        batch_size=8,
        transport=httpx.MockTransport(handler),
    )
    provider.embed_documents([str(index) for index in range(17)])
    assert request_sizes == [8, 8, 1]


def test_response_count_mismatch_in_later_batch_is_rejected() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        inputs = json.loads(request.content)["input"]
        count = len(inputs) if calls == 1 else len(inputs) - 1
        return httpx.Response(200, json={"embeddings": [[1.0]] * count})

    provider = OllamaEmbedder(
        "http://127.0.0.1:11434",
        "test-embed",
        batch_size=2,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingResponseError, match=r"batch 2/2, inputs 2-3"):
        provider.embed_documents(["a", "b", "c", "d"])


def test_inconsistent_dimensions_across_batches_are_rejected() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        dimension = 2 if calls == 1 else 3
        inputs = json.loads(request.content)["input"]
        return httpx.Response(
            200, json={"embeddings": [[1.0] * dimension for _ in inputs]}
        )

    provider = OllamaEmbedder(
        "http://127.0.0.1:11434",
        "test-embed",
        batch_size=2,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingResponseError, match=r"batch 2/2, inputs 2-3"):
        provider.embed_documents(["a", "b", "c", "d"])


def test_middle_batch_timeout_has_safe_context_without_input_text() -> None:
    calls = 0
    secret_text = "confidential-source-text"

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise httpx.ReadTimeout("timeout", request=request)
        inputs = json.loads(request.content)["input"]
        return httpx.Response(200, json={"embeddings": [[1.0] for _ in inputs]})

    provider = OllamaEmbedder(
        "http://127.0.0.1:11434",
        "test-embed",
        batch_size=2,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(EmbeddingUnavailableError) as caught:
        provider.embed_documents(["a", "b", secret_text, "d", "e"])
    assert "batch 2/3, inputs 2-3" in str(caught.value)
    assert secret_text not in str(caught.value)


@pytest.mark.parametrize("batch_size", [0, -1, True, 1.5, "8"])
def test_invalid_batch_sizes_are_rejected(batch_size: object) -> None:
    with pytest.raises(EmbeddingConfigurationError):
        OllamaEmbedder(
            "http://127.0.0.1:11434",
            "test-embed",
            batch_size=batch_size,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"embeddings": []},
        {"embeddings": [[]]},
        {"embeddings": [["bad"]]},
        {"embeddings": [[1, 2], [1, 2, 3]]},
    ],
)
def test_malformed_embeddings_are_rejected(payload: object) -> None:
    texts = ["a", "b"] if payload == {"embeddings": [[1, 2], [1, 2, 3]]} else ["a"]
    with pytest.raises(EmbeddingResponseError):
        mock_embedder(payload).embed_documents(texts)


def test_empty_embedding_input_is_rejected() -> None:
    with pytest.raises(EmbeddingConfigurationError):
        mock_embedder({"embeddings": [[1]]}).embed_documents([])
    with pytest.raises(EmbeddingConfigurationError):
        mock_embedder({"embeddings": [[1]]}).embed_query(" ")


def test_normalization_preserves_source_and_identifiers() -> None:
    source = "  WARNING\r\n\r\n\r\nSRVO-199 uses T1 mode.\n"
    original_hash = hashlib.sha256(source.encode()).hexdigest()
    normalized = normalize_embedding_input(source)
    assert source.endswith("\n")
    assert hashlib.sha256(source.encode()).hexdigest() == original_hash
    assert normalized == "WARNING\n\nSRVO-199 uses T1 mode."
    assert sha256_text(normalized) == sha256_text(normalized)


def test_point_id_is_deterministic() -> None:
    import uuid

    index_id = uuid.UUID("f37f807c-acbe-4478-a18c-b318826fd547")
    assert point_id(index_id, "CHK-1") == point_id(index_id, "CHK-1")
    assert point_id(index_id, "CHK-1") != point_id(index_id, "CHK-2")


def test_qdrant_local_mode_persists_and_searches(tmp_path: Path) -> None:
    import uuid

    path = tmp_path / "qdrant"
    store = QdrantLocalStore(path)
    store.create_collection("test_index", 2, "cosine")
    identifier = uuid.uuid4()
    store.upsert(
        "test_index",
        [(identifier, [1.0, 0.0], {"chunk_id": "CHK-1"})],
    )
    assert store.count("test_index") == 1
    result = store.search("test_index", [1.0, 0.0], 1)
    assert result[0].point_id == str(identifier)
    assert result[0].payload["chunk_id"] == "CHK-1"
    store.close()


def test_qdrant_context_closes_on_success_and_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    client = Mock()
    monkeypatch.setattr("apps.knowledge_base.indexing.QdrantClient", lambda **_: client)
    with QdrantLocalStore(tmp_path):
        pass
    client.close.assert_called_once()
    client.reset_mock()
    with pytest.raises(RuntimeError):
        with QdrantLocalStore(tmp_path):
            raise RuntimeError("build failed")
    client.close.assert_called_once()


@pytest.mark.django_db
def test_failed_batch_marks_candidate_failed_and_preserves_active(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active = VectorIndexVersion.objects.create(
        collection_name="active_collection",
        status=VectorIndexVersion.Status.ACTIVE,
        provider="ollama",
        model_name="test-embed",
        model_identity="ollama:test-embed:unreported",
        vector_dimension=2,
        distance_metric="cosine",
        normalization="provider-defined",
        corpus_fingerprint="a" * 64,
    )
    chunks = [
        SimpleNamespace(
            chunk_id="CHK-1",
            content="first",
            content_hash="b" * 64,
        )
    ]
    monkeypatch.setattr("apps.knowledge_base.indexing.eligible_chunks", lambda: chunks)
    embedder = Mock()
    embedder.get_configured_identity.return_value = SimpleNamespace(
        provider="ollama",
        model="test-embed",
        stable_identity="ollama:test-embed:unreported",
        dimension=0,
        distance_metric="cosine",
        normalization="provider-defined",
    )
    embedder.embed_documents.side_effect = EmbeddingUnavailableError(
        "Embedding request timed out for batch 1/1, inputs 0-0."
    )
    store = Mock()
    with pytest.raises(EmbeddingUnavailableError):
        build_index(embedder, store)
    active.refresh_from_db()
    failed = VectorIndexVersion.objects.get(status=VectorIndexVersion.Status.FAILED)
    assert active.status == VectorIndexVersion.Status.ACTIVE
    assert failed.failure_detail == "EmbeddingUnavailableError"
    store.create_collection.assert_not_called()


def test_embed_query_remains_one_validated_request() -> None:
    requests: list[list[str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        inputs = json.loads(request.content)["input"]
        requests.append(inputs)
        return httpx.Response(200, json={"embeddings": [[0.0] * 1024]})

    provider = OllamaEmbedder(
        "http://127.0.0.1:11434",
        "qwen3-embedding:0.6b",
        batch_size=16,
        transport=httpx.MockTransport(handler),
    )
    assert len(provider.embed_query("one query")) == 1024
    assert requests == [["one query"]]
    assert provider.get_model_identity().dimension == 1024


def retrieval_chunk(
    chunk_id: str,
    *,
    warning: bool = False,
    caution: bool = False,
    content_hash: str = "source-hash",
) -> DocumentChunk:
    return cast(
        DocumentChunk,
        SimpleNamespace(
            chunk_id=chunk_id,
            document_id="FANUC-B-80687EN-12",
            document_version_id="FANUC-version",
            chapter="3",
            section=chunk_id,
            page_start=1,
            page_end=1,
            contains_warning=warning,
            contains_caution=caution,
            content_hash=content_hash,
            content=f"Content for {chunk_id}",
        ),
    )


def candidate(chunk_id: str, score: float) -> VectorCandidate:
    return VectorCandidate(
        point_id=f"point-{chunk_id}",
        score=score,
        payload={"chunk_id": chunk_id, "source_content_hash": "source-hash"},
    )


def test_dense_ranking_remains_similarity_ordered() -> None:
    valid = [
        (candidate("warning", 0.29), retrieval_chunk("warning", warning=True)),
        (candidate("t2", 0.49539), retrieval_chunk("t2")),
        (candidate("t1", 0.49827), retrieval_chunk("t1")),
    ]
    ranked = _rank_candidates(valid, safety_first=False)
    assert [item.chunk.chunk_id for item in ranked] == ["t1", "t2", "warning"]
    assert all(item.ranking_score == item.semantic_score for item in ranked)


def test_safety_first_does_not_promote_unrelated_warning_or_caution() -> None:
    valid = [
        (
            candidate("hot-caution", 0.28675),
            retrieval_chunk("hot-caution", caution=True),
        ),
        (
            candidate("stop-warning", 0.29384),
            retrieval_chunk("stop-warning", warning=True),
        ),
        (candidate("t2", 0.49539), retrieval_chunk("t2")),
        (candidate("t1", 0.49827), retrieval_chunk("t1")),
    ]
    ranked = _rank_candidates(valid, safety_first=True)
    assert [item.chunk.chunk_id for item in ranked] == [
        "t1",
        "t2",
        "stop-warning",
        "hot-caution",
    ]


def test_relevant_warning_receives_bounded_explainable_priority() -> None:
    valid = [
        (candidate("plain", 0.50), retrieval_chunk("plain")),
        (
            candidate("relevant-warning", 0.49),
            retrieval_chunk("relevant-warning", warning=True),
        ),
    ]
    ranked = _rank_candidates(valid, safety_first=True)
    promoted = ranked[0]
    assert promoted.chunk.chunk_id == "relevant-warning"
    assert 0 < promoted.safety_priority_applied <= 0.02
    assert promoted.ranking_score == pytest.approx(
        promoted.semantic_score + promoted.safety_priority_applied
    )
    assert promoted.ranking_reason == (
        "semantic_similarity_plus_bounded_safety_priority"
    )


def test_safety_ranking_ties_are_deterministic() -> None:
    valid = [
        (candidate("chunk-b", 0.5), retrieval_chunk("chunk-b")),
        (candidate("chunk-a", 0.5), retrieval_chunk("chunk-a")),
    ]
    ranked = _rank_candidates(valid, safety_first=True)
    assert [item.chunk.chunk_id for item in ranked] == ["chunk-a", "chunk-b"]


class FakeEligibleChunks(list[DocumentChunk]):
    def filter(self, **filters: object) -> "FakeEligibleChunks":
        raw_allowed = filters.get("chunk_id__in", [])
        allowed = set(cast(list[str], raw_allowed))
        document_id = filters.get("document_id")
        return FakeEligibleChunks(
            chunk
            for chunk in self
            if (not allowed or chunk.chunk_id in allowed)
            and (document_id is None or chunk.document_id == document_id)
        )


@pytest.mark.django_db
def test_minimum_score_abstention_deduplication_and_provenance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    VectorIndexVersion.objects.create(
        collection_name="retrieval_index",
        status=VectorIndexVersion.Status.ACTIVE,
        provider="ollama",
        model_name="test",
        model_identity="ollama:test:unreported",
        vector_dimension=2,
        distance_metric="cosine",
        normalization="provider-defined",
        corpus_fingerprint="c" * 64,
    )
    weather = retrieval_chunk("weather-nearest", warning=True)
    ineligible = retrieval_chunk("superseded")
    monkeypatch.setattr(
        "apps.knowledge_base.retrieval.eligible_chunks",
        lambda: FakeEligibleChunks([weather]),
    )
    store = Mock()
    store.search.return_value = [
        candidate("weather-nearest", 0.29313),
        candidate("weather-nearest", 0.29313),
        candidate("superseded", 0.8),
    ]
    embedder = Mock()
    embedder.embed_query.return_value = [1.0, 0.0]
    results = retrieve(
        "What is the weather forecast tomorrow?",
        embedder,
        store,
        minimum_score=0.35,
        safety_first=True,
    )
    assert results == []
    assert ineligible.chunk_id not in [result.chunk_id for result in results]
    accepted = retrieve(
        "What is the weather forecast tomorrow?",
        embedder,
        store,
        minimum_score=0.2,
        safety_first=True,
    )
    assert [result.chunk_id for result in accepted] == ["weather-nearest"]


@pytest.mark.django_db
def test_retrieved_warning_metadata_and_scores_are_consistent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    VectorIndexVersion.objects.create(
        collection_name="metadata_index",
        status=VectorIndexVersion.Status.ACTIVE,
        provider="ollama",
        model_name="test",
        model_identity="ollama:test:unreported",
        vector_dimension=2,
        distance_metric="cosine",
        normalization="provider-defined",
        corpus_fingerprint="d" * 64,
    )
    warning = retrieval_chunk("relevant-warning", warning=True)
    monkeypatch.setattr(
        "apps.knowledge_base.retrieval.eligible_chunks",
        lambda: FakeEligibleChunks([warning]),
    )
    store = Mock()
    store.search.return_value = [candidate("relevant-warning", 0.49)]
    embedder = Mock()
    embedder.embed_query.return_value = [1.0, 0.0]
    result = retrieve(
        "relevant safety query",
        embedder,
        store,
        minimum_score=0.35,
        safety_first=True,
    )[0]
    assert result.contains_warning is True
    assert result.contains_caution is False
    assert result.score == result.semantic_score
    assert result.ranking_score == pytest.approx(
        result.semantic_score + result.safety_priority_applied
    )


@pytest.mark.django_db
def test_retrieval_inspector_denies_anonymous(client: Any) -> None:
    response = client.get("/staff/retrieval/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_retrieval_inspector_denies_non_staff(
    client: Any, django_user_model: Any
) -> None:
    user = django_user_model.objects.create_user("viewer", password="test-password")
    client.force_login(user)
    response = client.get("/staff/retrieval/")
    assert response.status_code == 302


@pytest.mark.django_db
def test_retrieval_inspector_allows_staff_without_llm_call(
    client: Any, django_user_model: Any
) -> None:
    user = django_user_model.objects.create_user(
        "staff-viewer", password="test-password", is_staff=True
    )
    client.force_login(user)
    response = client.get("/staff/retrieval/")
    assert response.status_code == 200
    assert b"No LLM answer is generated" in response.content
