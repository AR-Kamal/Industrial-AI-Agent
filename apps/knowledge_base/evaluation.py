"""Human-reviewed retrieval evaluation and threshold calibration."""

import hashlib
import json
import math
import time
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import mean
from typing import Any

from .retrieval import RetrievedChunk

APPROVED = "approved"
PENDING = "pending_review"


@dataclass(frozen=True)
class EvaluationCase:
    question_id: str
    question: str
    category: str
    expected_document_id: str
    expected_chapter: str
    expected_section: str
    acceptable_chunk_ids: tuple[str, ...]
    safety_critical: bool
    exact_identifier: bool
    numeric_value: bool
    expected_no_result: bool
    required_top_k: int
    review_status: str
    reviewer: str
    notes: str


Retriever = Callable[
    [EvaluationCase, float | None, str, int, str | None],
    list[RetrievedChunk],
]


def load_dataset(
    path: Path,
) -> tuple[dict[str, Any], list[EvaluationCase], list[dict[str, str]]]:
    raw_bytes = path.read_bytes()
    payload = json.loads(raw_bytes)
    if not isinstance(payload, dict) or not isinstance(payload.get("cases"), list):
        raise ValueError("Evaluation dataset must contain a cases list.")
    cases: list[EvaluationCase] = []
    invalid: list[dict[str, str]] = []
    for position, raw in enumerate(payload["cases"], start=1):
        try:
            cases.append(_parse_case(raw))
        except (KeyError, TypeError, ValueError) as exc:
            invalid.append({"position": str(position), "reason": str(exc)})
    metadata = {
        "dataset_version": str(payload.get("dataset_version", "")),
        "dataset_review_status": str(payload.get("review_status", "")),
        "dataset_sha256": hashlib.sha256(raw_bytes).hexdigest(),
        "dataset_path": str(path),
    }
    return metadata, cases, invalid


def _parse_case(raw: object) -> EvaluationCase:
    if not isinstance(raw, dict):
        raise TypeError("Case must be an object.")
    required_strings = ("question_id", "question", "category", "review_status")
    for field in required_strings:
        if not isinstance(raw.get(field), str) or not str(raw[field]).strip():
            raise ValueError(f"{field} must be a non-empty string.")
    status = str(raw["review_status"])
    if status not in {APPROVED, PENDING}:
        raise ValueError("review_status must be approved or pending_review.")
    acceptable = raw.get("acceptable_chunk_ids", [])
    if not isinstance(acceptable, list) or not all(
        isinstance(item, str) and item for item in acceptable
    ):
        raise ValueError("acceptable_chunk_ids must be a list of non-empty strings.")
    top_k = raw.get("required_top_k", 5)
    if isinstance(top_k, bool) or not isinstance(top_k, int) or top_k < 1:
        raise ValueError("required_top_k must be a positive integer.")
    expected_no_result = bool(raw.get("expected_no_result", False))
    has_expectation = bool(
        acceptable
        or raw.get("expected_document_id")
        or raw.get("expected_chapter")
        or raw.get("expected_section")
    )
    if not expected_no_result and not has_expectation:
        raise ValueError("Supported case requires an expected source locator.")
    return EvaluationCase(
        question_id=str(raw["question_id"]),
        question=str(raw["question"]),
        category=str(raw["category"]),
        expected_document_id=str(raw.get("expected_document_id", "")),
        expected_chapter=str(raw.get("expected_chapter", "")),
        expected_section=str(raw.get("expected_section", "")),
        acceptable_chunk_ids=tuple(acceptable),
        safety_critical=bool(raw.get("safety_critical", False)),
        exact_identifier=bool(raw.get("exact_identifier", False)),
        numeric_value=bool(raw.get("numeric_value", False)),
        expected_no_result=expected_no_result,
        required_top_k=top_k,
        review_status=status,
        reviewer=str(raw.get("reviewer", "")),
        notes=str(raw.get("notes", "")),
    )


def evaluate(
    cases: Sequence[EvaluationCase],
    retriever: Retriever,
    *,
    retrieval_mode: str,
    threshold: float | None,
    top_k: int,
    document_id: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    outcomes = [
        _evaluate_case(
            case,
            retriever,
            retrieval_mode=retrieval_mode,
            threshold=threshold,
            top_k=max(top_k, case.required_top_k),
            document_id=document_id,
        )
        for case in cases
        if case.review_status == APPROVED
    ]
    return outcomes, calculate_metrics(outcomes)


def _evaluate_case(
    case: EvaluationCase,
    retriever: Retriever,
    *,
    retrieval_mode: str,
    threshold: float | None,
    top_k: int,
    document_id: str | None,
) -> dict[str, Any]:
    started = time.perf_counter()
    results = retriever(case, threshold, retrieval_mode, top_k, document_id)
    latency_ms = (time.perf_counter() - started) * 1000
    expected_rank = _expected_rank(case, results)
    abstained = not results
    passed = abstained if case.expected_no_result else expected_rank is not None
    if case.expected_no_result and results:
        failure_reason = "negative_query_not_abstained"
    elif not case.expected_no_result and abstained:
        failure_reason = "supported_query_false_abstention"
    elif not case.expected_no_result and expected_rank is None:
        failure_reason = "expected_source_not_retrieved"
    else:
        failure_reason = ""
    provenance_complete = all(_complete_provenance(result) for result in results)
    if results and not provenance_complete and not failure_reason:
        failure_reason = "incomplete_provenance"
        passed = False
    return {
        "question_id": case.question_id,
        "query": case.question,
        "category": case.category,
        "retrieval_mode": retrieval_mode,
        "configured_threshold": threshold,
        "returned_chunk_ids": [result.chunk_id for result in results],
        "expected_chunk_rank": expected_rank,
        "top_semantic_score": results[0].semantic_score if results else None,
        "top_ranking_score": results[0].ranking_score if results else None,
        "accepted": bool(results),
        "abstained": abstained,
        "passed": passed,
        "failure_reason": failure_reason,
        "latency_ms": latency_ms,
        "provenance_complete": provenance_complete,
        "expected_no_result": case.expected_no_result,
        "safety_critical": case.safety_critical,
        "exact_identifier": case.exact_identifier,
        "numeric_value": case.numeric_value,
        "numeric_or_standards": case.numeric_value
        or "standard" in case.category.lower(),
        "results": [asdict(result) for result in results],
    }


def _expected_rank(
    case: EvaluationCase, results: Sequence[RetrievedChunk]
) -> int | None:
    for result in results:
        if case.acceptable_chunk_ids and result.chunk_id in case.acceptable_chunk_ids:
            return result.rank
        if case.acceptable_chunk_ids:
            continue
        if (
            case.expected_document_id
            and result.document_id != case.expected_document_id
        ):
            continue
        if case.expected_chapter and result.chapter != case.expected_chapter:
            continue
        if case.expected_section and result.section != case.expected_section:
            continue
        if case.expected_document_id or case.expected_chapter or case.expected_section:
            return result.rank
    return None


def _complete_provenance(result: RetrievedChunk) -> bool:
    return bool(
        result.chunk_id
        and result.document_id
        and result.document_version_id
        and result.source_content_hash
        and result.index_version_id
        and result.retrieval_mode
        and result.ranking_reason
    )


def calculate_metrics(outcomes: Sequence[dict[str, Any]]) -> dict[str, Any]:
    supported = [item for item in outcomes if not item["expected_no_result"]]
    negative = [item for item in outcomes if item["expected_no_result"]]
    ranks = [item["expected_chunk_rank"] for item in supported]
    latencies = [float(item["latency_ms"]) for item in outcomes]
    return {
        "approved_case_count": len(outcomes),
        "hit_at_1": _rate(ranks, lambda rank: rank is not None and rank <= 1),
        "hit_at_3": _rate(ranks, lambda rank: rank is not None and rank <= 3),
        "hit_at_5": _rate(ranks, lambda rank: rank is not None and rank <= 5),
        "mean_reciprocal_rank": (
            mean(1 / rank if rank else 0 for rank in ranks) if ranks else None
        ),
        "safety_critical_hit_at_3": _subset_hit(outcomes, "safety_critical"),
        "exact_identifier_hit_at_3": _subset_hit(outcomes, "exact_identifier"),
        "numeric_or_standards_hit_at_3": _subset_hit(outcomes, "numeric_or_standards"),
        "negative_query_abstention_rate": _rate(
            negative, lambda item: bool(item["abstained"])
        ),
        "supported_query_false_abstention_rate": _rate(
            supported, lambda item: bool(item["abstained"])
        ),
        "average_latency_ms": mean(latencies) if latencies else None,
        "p95_latency_ms": percentile(latencies, 95),
        "provenance_completeness": _rate(
            outcomes, lambda item: bool(item["provenance_complete"])
        ),
        "highest_supported_semantic_score": _highest_score(supported),
        "highest_negative_semantic_score": _highest_score(negative),
        "lowest_accepted_supported_semantic_score": _lowest_accepted_score(supported),
        "supported_score_distribution": _score_distribution(supported),
        "negative_score_distribution": _score_distribution(negative),
    }


def calibration(
    cases: Sequence[EvaluationCase],
    retriever: Retriever,
    thresholds: Sequence[float],
    *,
    retrieval_mode: str,
    top_k: int,
    document_id: str | None,
) -> list[dict[str, Any]]:
    rows = []
    for threshold in sorted(set(thresholds)):
        outcomes, metrics = evaluate(
            cases,
            retriever,
            retrieval_mode=retrieval_mode,
            threshold=threshold,
            top_k=top_k,
            document_id=document_id,
        )
        supported = [item for item in outcomes if not item["expected_no_result"]]
        negative = [item for item in outcomes if item["expected_no_result"]]
        rows.append(
            {
                "threshold": threshold,
                "supported_query_recall": metrics["hit_at_5"],
                "false_abstention_rate": metrics[
                    "supported_query_false_abstention_rate"
                ],
                "negative_query_abstention_rate": metrics[
                    "negative_query_abstention_rate"
                ],
                "false_acceptance_rate": _rate(
                    negative, lambda item: bool(item["accepted"])
                ),
                "safety_critical_hit_at_3": metrics["safety_critical_hit_at_3"],
                "exact_identifier_hit_at_3": metrics["exact_identifier_hit_at_3"],
                "supported_count": len(supported),
                "negative_count": len(negative),
                "highest_supported_semantic_score": metrics[
                    "highest_supported_semantic_score"
                ],
                "highest_negative_semantic_score": metrics[
                    "highest_negative_semantic_score"
                ],
                "lowest_accepted_supported_semantic_score": metrics[
                    "lowest_accepted_supported_semantic_score"
                ],
                "supported_score_distribution": metrics["supported_score_distribution"],
                "negative_score_distribution": metrics["negative_score_distribution"],
            }
        )
    return rows


def _subset_hit(outcomes: Sequence[dict[str, Any]], flag: str) -> float | None:
    subset = [
        item for item in outcomes if item[flag] and not item["expected_no_result"]
    ]
    return _rate(
        subset,
        lambda item: item["expected_chunk_rank"] is not None
        and item["expected_chunk_rank"] <= 3,
    )


def _rate(values: Sequence[Any], predicate: Callable[[Any], bool]) -> float | None:
    return (
        mean(1.0 if predicate(value) else 0.0 for value in values) if values else None
    )


def _highest_score(outcomes: Sequence[dict[str, Any]]) -> float | None:
    scores = [
        float(item["top_semantic_score"])
        for item in outcomes
        if item.get("top_semantic_score") is not None
    ]
    return max(scores) if scores else None


def _lowest_accepted_score(outcomes: Sequence[dict[str, Any]]) -> float | None:
    scores = [
        float(item["top_semantic_score"])
        for item in outcomes
        if item.get("accepted") and item.get("top_semantic_score") is not None
    ]
    return min(scores) if scores else None


def _score_distribution(outcomes: Sequence[dict[str, Any]]) -> dict[str, float] | None:
    scores = [
        float(item["top_semantic_score"])
        for item in outcomes
        if item.get("top_semantic_score") is not None
    ]
    if not scores:
        return None
    return {
        "minimum": min(scores),
        "p25": percentile(scores, 25) or 0.0,
        "median": percentile(scores, 50) or 0.0,
        "p75": percentile(scores, 75) or 0.0,
        "p95": percentile(scores, 95) or 0.0,
        "maximum": max(scores),
    }


def percentile(values: Sequence[float], percentile_value: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * percentile_value / 100
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def render_markdown(report: dict[str, Any]) -> str:
    counts = report["case_counts"]
    metrics = report.get("metrics", {})
    lines = [
        "# Retrieval evaluation report",
        "",
        f"- Timestamp: {report['timestamp']}",
        f"- Dataset: {report['dataset']['dataset_version']}",
        f"- Index: {report['index']['id']}",
        f"- Model: {report['index']['model_identity']}",
        f"- Retrieval mode: {report['retrieval_configuration']['mode']}",
        f"- Threshold: {report['retrieval_configuration']['threshold']}",
        f"- Approved cases: {counts['approved']}",
        f"- Pending cases: {counts['pending']}",
        f"- Invalid cases: {counts['invalid']}",
        f"- Skipped cases: {counts['skipped']}",
        "",
        "## Formal metrics (approved cases only)",
        "",
    ]
    for name, value in metrics.items():
        lines.append(f"- {name}: {value}")
    calibration_rows = report.get("threshold_calibration", [])
    if calibration_rows:
        lines.extend(["", "## Threshold calibration", ""])
        for row in calibration_rows:
            lines.append(
                "- threshold={threshold}: recall={supported_query_recall}, "
                "false_abstention={false_abstention_rate}, "
                "negative_abstention={negative_query_abstention_rate}, "
                "false_acceptance={false_acceptance_rate}".format(**row)
            )
    failures = [item for item in report.get("case_outcomes", []) if not item["passed"]]
    lines.extend(["", "## Failed approved cases", ""])
    if not failures:
        lines.append("None.")
    else:
        for item in failures:
            lines.append(
                f"- {item['question_id']}: {item['failure_reason']} "
                f"(rank={item['expected_chunk_rank']})"
            )
    lines.append("")
    return "\n".join(lines)
