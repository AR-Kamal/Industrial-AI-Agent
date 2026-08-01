import json
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command

from apps.knowledge_base.evaluation import (
    APPROVED,
    PENDING,
    EvaluationCase,
    calculate_metrics,
    calibration,
    evaluate,
    load_dataset,
    render_markdown,
)
from apps.knowledge_base.models import VectorIndexVersion
from apps.knowledge_base.retrieval import RetrievedChunk


def case(
    question_id: str,
    *,
    status: str = APPROVED,
    acceptable: tuple[str, ...] = ("expected",),
    negative: bool = False,
    safety: bool = False,
    exact: bool = False,
    numeric: bool = False,
) -> EvaluationCase:
    return EvaluationCase(
        question_id=question_id,
        question=f"Question {question_id}",
        category="test",
        expected_document_id="" if acceptable else "DOC-1",
        expected_chapter="",
        expected_section="",
        acceptable_chunk_ids=acceptable,
        safety_critical=safety,
        exact_identifier=exact,
        numeric_value=numeric,
        expected_no_result=negative,
        required_top_k=5,
        review_status=status,
        reviewer="reviewer",
        notes="",
    )


def result(chunk_id: str, rank: int, *, complete: bool = True) -> RetrievedChunk:
    return RetrievedChunk(
        rank=rank,
        score=0.5,
        semantic_score=0.5,
        ranking_score=0.5,
        safety_priority_applied=0.0,
        ranking_reason="semantic_similarity" if complete else "",
        retrieval_mode="dense",
        chunk_id=chunk_id,
        document_id="DOC-1",
        document_version_id="VER-1" if complete else "",
        chapter="3",
        section="Modes",
        page_start=1,
        page_end=1,
        contains_warning=False,
        contains_caution=False,
        source_content_hash="hash" if complete else "",
        index_version_id="index" if complete else "",
        content="content",
    )


def test_pending_cases_are_excluded_and_approved_cases_are_included() -> None:
    calls: list[str] = []

    def retriever(
        item: EvaluationCase,
        threshold: float | None,
        mode: str,
        top_k: int,
        document: str | None,
    ) -> list[RetrievedChunk]:
        calls.append(item.question_id)
        return [result("expected", 1)]

    outcomes, metrics = evaluate(
        [case("approved"), case("pending", status=PENDING)],
        retriever,
        retrieval_mode="dense",
        threshold=None,
        top_k=5,
        document_id=None,
    )
    assert calls == ["approved"]
    assert [item["question_id"] for item in outcomes] == ["approved"]
    assert metrics["approved_case_count"] == 1


def test_hit_metrics_mrr_subsets_and_multiple_acceptable_chunks() -> None:
    outcomes: list[dict[str, Any]] = [
        {
            "expected_no_result": False,
            "expected_chunk_rank": 1,
            "safety_critical": True,
            "exact_identifier": False,
            "numeric_value": False,
            "numeric_or_standards": False,
            "abstained": False,
            "latency_ms": 10.0,
            "provenance_complete": True,
        },
        {
            "expected_no_result": False,
            "expected_chunk_rank": 3,
            "safety_critical": False,
            "exact_identifier": True,
            "numeric_value": True,
            "numeric_or_standards": True,
            "abstained": False,
            "latency_ms": 20.0,
            "provenance_complete": True,
        },
        {
            "expected_no_result": False,
            "expected_chunk_rank": None,
            "safety_critical": False,
            "exact_identifier": False,
            "numeric_value": False,
            "numeric_or_standards": False,
            "abstained": True,
            "latency_ms": 30.0,
            "provenance_complete": True,
        },
    ]
    metrics = calculate_metrics(outcomes)
    assert metrics["hit_at_1"] == pytest.approx(1 / 3)
    assert metrics["hit_at_3"] == pytest.approx(2 / 3)
    assert metrics["hit_at_5"] == pytest.approx(2 / 3)
    assert metrics["mean_reciprocal_rank"] == pytest.approx((1 + 1 / 3) / 3)
    assert metrics["safety_critical_hit_at_3"] == 1
    assert metrics["exact_identifier_hit_at_3"] == 1
    assert metrics["numeric_or_standards_hit_at_3"] == 1

    def retriever(
        item: EvaluationCase,
        threshold: float | None,
        mode: str,
        top_k: int,
        document: str | None,
    ) -> list[RetrievedChunk]:
        return [result("alternate", 1)]

    evaluated, _ = evaluate(
        [case("multiple", acceptable=("expected", "alternate"))],
        retriever,
        retrieval_mode="dense",
        threshold=None,
        top_k=5,
        document_id=None,
    )
    assert evaluated[0]["expected_chunk_rank"] == 1


def test_false_abstention_negative_abstention_and_provenance() -> None:
    def retriever(
        item: EvaluationCase,
        threshold: float | None,
        mode: str,
        top_k: int,
        document: str | None,
    ) -> list[RetrievedChunk]:
        if item.question_id in {"supported", "negative"}:
            return []
        return [result("expected", 1, complete=False)]

    outcomes, metrics = evaluate(
        [case("supported"), case("negative", negative=True), case("incomplete")],
        retriever,
        retrieval_mode="dense",
        threshold=0.4,
        top_k=5,
        document_id=None,
    )
    assert metrics["supported_query_false_abstention_rate"] == 0.5
    assert metrics["negative_query_abstention_rate"] == 1
    incomplete = next(item for item in outcomes if item["question_id"] == "incomplete")
    assert incomplete["passed"] is False
    assert incomplete["failure_reason"] == "incomplete_provenance"


def test_threshold_calibration_reports_tradeoffs_without_selection() -> None:
    def retriever(
        item: EvaluationCase,
        threshold: float | None,
        mode: str,
        top_k: int,
        document: str | None,
    ) -> list[RetrievedChunk]:
        score = 0.5 if not item.expected_no_result else 0.3
        return (
            [result("expected", 1)] if threshold is None or score >= threshold else []
        )

    rows = calibration(
        [case("positive"), case("negative", negative=True)],
        retriever,
        [0.2, 0.4],
        retrieval_mode="dense",
        top_k=5,
        document_id=None,
    )
    assert rows[0]["false_acceptance_rate"] == 1
    assert rows[0]["negative_query_abstention_rate"] == 0
    assert rows[1]["supported_query_recall"] == 1
    assert rows[1]["negative_query_abstention_rate"] == 1
    assert rows[0]["supported_score_distribution"]["median"] == 0.5
    assert rows[0]["negative_score_distribution"]["maximum"] == 0.5


def test_invalid_records_and_empty_approved_dataset(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.json"
    dataset.write_text(
        json.dumps(
            {
                "dataset_version": "test",
                "cases": [
                    {"question_id": "broken"},
                    {
                        "question_id": "pending",
                        "question": "Pending question",
                        "category": "test",
                        "review_status": PENDING,
                        "expected_no_result": True,
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    _, cases, invalid = load_dataset(dataset)
    assert len(invalid) == 1

    def must_not_retrieve(
        item: EvaluationCase,
        threshold: float | None,
        mode: str,
        top_k: int,
        document: str | None,
    ) -> list[RetrievedChunk]:
        pytest.fail("pending case must not invoke retrieval")

    outcomes, metrics = evaluate(
        cases,
        must_not_retrieve,
        retrieval_mode="dense",
        threshold=None,
        top_k=5,
        document_id=None,
    )
    assert outcomes == []
    assert metrics["approved_case_count"] == 0
    assert metrics["hit_at_1"] is None


def test_markdown_output_is_deterministic() -> None:
    report = {
        "timestamp": "2026-08-01T00:00:00+00:00",
        "dataset": {"dataset_version": "v1"},
        "index": {"id": "index", "model_identity": "model"},
        "retrieval_configuration": {"mode": "dense", "threshold": 0.4},
        "case_counts": {"approved": 1, "pending": 0, "invalid": 0, "skipped": 0},
        "metrics": {"hit_at_1": 1.0},
        "threshold_calibration": [],
        "case_outcomes": [],
    }
    assert render_markdown(report) == render_markdown(report)


@pytest.mark.django_db
def test_command_uses_retrieval_service_and_writes_runtime_reports(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, settings: Any
) -> None:
    VectorIndexVersion.objects.create(
        collection_name="evaluation-index",
        status=VectorIndexVersion.Status.ACTIVE,
        provider="ollama",
        model_name="embed",
        model_identity="ollama:embed:digest",
        vector_dimension=1024,
        distance_metric="cosine",
        normalization="provider-defined",
        corpus_fingerprint="e" * 64,
    )
    dataset = tmp_path / "approved.json"
    dataset.write_text(
        json.dumps(
            {
                "dataset_version": "approved-v1",
                "review_status": APPROVED,
                "cases": [
                    {
                        "question_id": "A1",
                        "question": "Approved question",
                        "category": "test",
                        "acceptable_chunk_ids": ["expected"],
                        "expected_no_result": False,
                        "review_status": APPROVED,
                        "required_top_k": 5,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    settings.BASE_DIR = tmp_path
    fake_store = type(
        "StoreContext",
        (),
        {
            "__enter__": lambda self: self,
            "__exit__": lambda self, *args: None,
        },
    )()
    calls: list[str] = []
    monkeypatch.setattr(
        "apps.knowledge_base.management.commands.evaluate_retrieval.vector_store",
        lambda: fake_store,
    )
    monkeypatch.setattr(
        "apps.knowledge_base.management.commands.evaluate_retrieval.embedding_provider",
        lambda: object(),
    )

    def fake_retrieve(
        query: str, *args: object, **kwargs: object
    ) -> list[RetrievedChunk]:
        calls.append(query)
        return [result("expected", 1)]

    monkeypatch.setattr(
        "apps.knowledge_base.management.commands.evaluate_retrieval.retrieve",
        fake_retrieve,
    )
    call_command(
        "evaluate_retrieval",
        dataset=str(dataset),
        output="report.json",
        approved_only=True,
    )
    assert calls == ["Approved question"]
    report_path = tmp_path / "var" / "evaluation" / "report.json"
    assert report_path.exists()
    assert report_path.with_suffix(".md").exists()
    payload = json.loads(report_path.read_text(encoding="utf-8"))
    assert payload["metrics"]["hit_at_1"] == 1
    assert payload["case_counts"]["approved"] == 1
