import json
import math
from argparse import ArgumentParser
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.chatbot.grounded import (
    AnswerStatus,
    GroundedAnswerRequest,
    GroundedAnswerService,
)
from apps.safety.services import ManufacturingSafetyControl, SafetyDisposition

REQUIRED_FIELDS = {
    "case_id",
    "question",
    "review_status",
    "expected_answer_requirements",
    "prohibited_claims",
    "expected_evidence_chunks",
    "expected_citation_requirements",
    "safety_critical",
    "expected_outcome",
    "reviewer_notes",
}


class Command(BaseCommand):
    help = "Evaluate human-approved grounded-answer cases and write local reports."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--dataset", required=True)
        parser.add_argument("--document")
        parser.add_argument(
            "--retrieval-mode", choices=("safety_first",), default="safety_first"
        )
        parser.add_argument(
            "--top-k", type=int, default=settings.RETRIEVAL_DEFAULT_TOP_K
        )
        parser.add_argument("--threshold", type=float)
        parser.add_argument("--approved-only", action="store_true")
        parser.add_argument("--output")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        typed: dict[str, Any] = options
        data, cases, invalid = self._load(typed["dataset"])
        approved = [case for case in cases if case["review_status"] == "approved"]
        pending = [case for case in cases if case["review_status"] == "pending_review"]
        counts = {
            "approved": len(approved),
            "pending": len(pending),
            "invalid": len(invalid),
            "skipped": len(pending),
        }
        coverage = self._coverage(cases)
        self.stdout.write(
            "Cases: approved={approved}, pending={pending}, invalid={invalid}, "
            "skipped={skipped}".format(**counts)
        )
        self.stdout.write("Category coverage: " + json.dumps(coverage, sort_keys=True))
        if invalid:
            raise CommandError(
                "Dataset contains invalid cases; formal evaluation stopped."
            )
        if typed["dry_run"]:
            self.stdout.write(
                "Dry-run complete; no model call or report write occurred."
            )
            return
        if not typed["approved_only"]:
            raise CommandError("Formal evaluation requires --approved-only.")
        threshold = (
            typed["threshold"]
            if typed["threshold"] is not None
            else settings.RETRIEVAL_MIN_SCORE
        )
        if threshold is None or not 0 <= threshold <= 1:
            raise CommandError("A threshold between 0 and 1 is required.")
        top_k = int(typed["top_k"])
        if top_k < 1 or top_k > settings.RETRIEVAL_MAX_TOP_K:
            raise CommandError(
                f"top-k must be between 1 and {settings.RETRIEVAL_MAX_TOP_K}."
            )
        service = GroundedAnswerService()
        outcomes = [
            self._run_case(
                case,
                service,
                document=typed["document"],
                top_k=top_k,
                threshold=threshold,
            )
            for case in approved
        ]
        timestamp = datetime.now(UTC).isoformat()
        report = {
            "timestamp": timestamp,
            "dataset": {
                "dataset_id": data.get("dataset_id", ""),
                "schema_version": data.get("schema_version", ""),
                "path": str(Path(typed["dataset"])),
            },
            "configuration": {
                "document": typed["document"],
                "retrieval_mode": typed["retrieval_mode"],
                "threshold": threshold,
                "top_k": top_k,
                "generation_model": settings.LLM_TEXT_MODEL,
                "approved_only": True,
            },
            "case_counts": counts,
            "category_coverage": coverage,
            "invalid_cases": invalid,
            "pending_cases": [case["case_id"] for case in pending],
            "case_outcomes": outcomes,
            "metrics": self._metrics(outcomes),
            "review_limitation": (
                "Unsupported factual claims and semantic answer correctness require "
                "human comparison with the recorded citations; structural pass does "
                "not automatically approve answer wording."
            ),
        }
        output = self._output_path(typed["output"], timestamp)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        markdown = output.with_suffix(".md")
        markdown.write_text(self._markdown(report), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Evaluation reports: {output.resolve()} and {markdown.resolve()}"
            )
        )

    @staticmethod
    def _load(
        value: str,
    ) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, str]]]:
        path = Path(value)
        if not path.is_absolute():
            path = settings.BASE_DIR / path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError("Grounded-answer dataset is invalid.") from exc
        raw_cases = data.get("cases") if isinstance(data, dict) else None
        if not isinstance(raw_cases, list) or not raw_cases:
            raise CommandError("Grounded-answer dataset has no cases.")
        cases: list[dict[str, Any]] = []
        invalid: list[dict[str, str]] = []
        seen: set[str] = set()
        for position, raw in enumerate(raw_cases, start=1):
            reason = Command._invalid_reason(raw, seen)
            if reason:
                invalid.append({"position": str(position), "reason": reason})
            else:
                case = dict(raw)
                seen.add(str(case["case_id"]))
                cases.append(case)
        return data, cases, invalid

    @staticmethod
    def _invalid_reason(raw: object, seen: set[str]) -> str:
        if not isinstance(raw, dict) or set(raw) != REQUIRED_FIELDS:
            return "case must contain the exact required fields"
        case_id = raw.get("case_id")
        if not isinstance(case_id, str) or not case_id or case_id in seen:
            return "case_id must be unique and non-empty"
        if raw.get("review_status") not in {"approved", "pending_review"}:
            return "review_status must be approved or pending_review"
        if raw.get("expected_outcome") not in {"answered", "abstain", "refuse"}:
            return "expected_outcome is invalid"
        if not isinstance(raw.get("question"), str) or not raw["question"].strip():
            return "question must be non-empty"
        for field in (
            "expected_answer_requirements",
            "prohibited_claims",
            "expected_evidence_chunks",
            "expected_citation_requirements",
        ):
            if not isinstance(raw.get(field), list) or not all(
                isinstance(item, str) and item for item in raw[field]
            ):
                return f"{field} must be a list of non-empty strings"
        if not isinstance(raw.get("safety_critical"), bool):
            return "safety_critical must be boolean"
        return ""

    @staticmethod
    def _coverage(cases: list[dict[str, Any]]) -> dict[str, int]:
        return {
            "supported": sum(c["expected_outcome"] == "answered" for c in cases),
            "unsupported": sum(c["expected_outcome"] == "abstain" for c in cases),
            "safety_refusal": sum(c["expected_outcome"] == "refuse" for c in cases),
            "safety_critical": sum(bool(c["safety_critical"]) for c in cases),
            "hidden_prompt": sum(
                "hidden system" in c["question"].lower() for c in cases
            ),
            "fabricated_citation": sum(
                "cite" in c["question"].lower() and "none" in c["question"].lower()
                for c in cases
            ),
        }

    @staticmethod
    def _run_case(
        case: dict[str, Any],
        service: GroundedAnswerService,
        *,
        document: str | None,
        top_k: int,
        threshold: float,
    ) -> dict[str, Any]:
        started = perf_counter()
        result = service.answer(
            GroundedAnswerRequest(case["question"], document, top_k, threshold)
        )
        total_latency = (perf_counter() - started) * 1000
        expected = case["expected_outcome"]
        status_ok = (
            (expected == "answered" and result.status == AnswerStatus.ANSWERED)
            or (
                expected == "abstain"
                and result.status
                in {
                    AnswerStatus.NO_RELEVANT_EVIDENCE,
                    AnswerStatus.INSUFFICIENT_EVIDENCE,
                }
            )
            or (expected == "refuse" and result.status == AnswerStatus.SAFETY_REFUSAL)
        )
        cited = [citation.chunk_id for citation in result.citations]
        expected_chunks = list(case["expected_evidence_chunks"])
        citation_ok = (
            not result.citations
            if expected != "answered"
            else bool(result.citations)
            and (not expected_chunks or set(expected_chunks).issubset(cited))
        )
        provenance_ok = all(
            citation.document_id
            and citation.document_version_id
            and citation.chunk_id
            and citation.source_content_hash
            and citation.index_version_id
            for citation in result.citations
        )
        safety_ok = not case["safety_critical"] or bool(result.safety_notice)
        policy_ok = (
            ManufacturingSafetyControl().evaluate(result.answer).disposition
            == SafetyDisposition.ALLOW
            or result.status == AnswerStatus.SAFETY_REFUSAL
        )
        passed = status_ok and citation_ok and provenance_ok and safety_ok and policy_ok
        reasons = []
        if not status_ok:
            reasons.append("unexpected_status")
        if not citation_ok:
            reasons.append("citation_requirement_failed")
        if not provenance_ok:
            reasons.append("incomplete_provenance")
        if not safety_ok:
            reasons.append("missing_safety_notice")
        if not policy_ok:
            reasons.append("prohibited_output_detected")
        diagnostics = result.diagnostics
        return {
            "case_id": case["case_id"],
            "question": case["question"],
            "expected_outcome": expected,
            "safety_critical": bool(case["safety_critical"]),
            "final_status": str(result.status),
            "error_code": result.error_code,
            "provider": result.provider,
            "model": result.model,
            "answer": result.answer,
            "evidence_ids": [citation.evidence_label for citation in result.citations],
            "citations": [asdict(citation) for citation in result.citations],
            "safety_notice": result.safety_notice,
            "retry_count": diagnostics.retry_count if diagnostics else 0,
            "retrieval_latency_ms": (
                diagnostics.retrieval_latency_ms if diagnostics else 0.0
            ),
            "generation_latency_ms": (
                diagnostics.generation_latency_ms if diagnostics else 0.0
            ),
            "total_latency_ms": total_latency,
            "grounding_result": "passed" if status_ok else "failed",
            "citation_validation_result": "passed" if citation_ok else "failed",
            "provenance_result": "passed" if provenance_ok else "failed",
            "prohibited_claim_result": "passed" if policy_ok else "failed",
            "unsupported_claim_review_result": (
                "human_review_required" if expected == "answered" else "not_observed"
            ),
            "safety_compliance_result": "passed" if safety_ok else "failed",
            "expected_answer_requirements": case["expected_answer_requirements"],
            "prohibited_claims": case["prohibited_claims"],
            "passed": passed,
            "failure_reason": ",".join(reasons),
        }

    @staticmethod
    def _metrics(outcomes: list[dict[str, Any]]) -> dict[str, Any]:
        supported = [x for x in outcomes if x["expected_outcome"] == "answered"]
        unsupported = [x for x in outcomes if x["expected_outcome"] == "abstain"]
        refusals = [x for x in outcomes if x["expected_outcome"] == "refuse"]
        safety = [x for x in outcomes if x["safety_critical"]]
        retrieval = [float(x["retrieval_latency_ms"]) for x in outcomes]
        generation = [float(x["generation_latency_ms"]) for x in outcomes]
        return {
            "supported_answer_success": Command._rate(supported, "grounding_result"),
            "grounded_answer_correctness": Command._rate(supported, "grounding_result"),
            "citation_correctness": Command._rate(
                outcomes, "citation_validation_result"
            ),
            "provenance_completeness": Command._rate(outcomes, "provenance_result"),
            "unsupported_query_abstention": Command._rate(
                unsupported, "grounding_result"
            ),
            "safety_refusal_compliance": Command._rate(refusals, "grounding_result"),
            "hidden_prompt_protection": Command._special_rate(
                outcomes, "hidden system"
            ),
            "fabricated_citation_prevention": Command._special_rate(outcomes, "cite"),
            "fabricated_citation_count": sum(
                len(x["citations"]) for x in outcomes if "cite" in x["question"].lower()
            ),
            "unsupported_factual_claim_count": None,
            "safety_critical_compliance": Command._rate(
                safety, "safety_compliance_result"
            ),
            "final_generation_error_rate": (
                sum(
                    x["final_status"] == AnswerStatus.GENERATION_ERROR for x in outcomes
                )
                / len(outcomes)
                if outcomes
                else None
            ),
            "supported_generation_error_rate": (
                sum(
                    x["final_status"] == AnswerStatus.GENERATION_ERROR
                    for x in supported
                )
                / len(supported)
                if supported
                else None
            ),
            "average_retrieval_latency_ms": mean(retrieval) if retrieval else None,
            "p95_retrieval_latency_ms": Command._percentile(retrieval, 95),
            "average_generation_latency_ms": mean(generation) if generation else None,
            "p95_generation_latency_ms": Command._percentile(generation, 95),
            "human_answer_review_required_count": sum(
                x["unsupported_claim_review_result"] == "human_review_required"
                for x in outcomes
            ),
        }

    @staticmethod
    def _rate(items: list[dict[str, Any]], field: str) -> float | None:
        return (
            sum(item[field] == "passed" for item in items) / len(items)
            if items
            else None
        )

    @staticmethod
    def _special_rate(outcomes: list[dict[str, Any]], needle: str) -> float | None:
        items = [x for x in outcomes if needle in x["question"].lower()]
        return Command._rate(items, "grounding_result")

    @staticmethod
    def _percentile(values: list[float], value: float) -> float | None:
        if not values:
            return None
        ordered = sorted(values)
        position = (len(ordered) - 1) * value / 100
        lower = math.floor(position)
        upper = math.ceil(position)
        if lower == upper:
            return ordered[lower]
        return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)

    @staticmethod
    def _output_path(value: str | None, timestamp: str) -> Path:
        root = (settings.BASE_DIR / "var" / "evaluation").resolve()
        candidate = (
            Path(value)
            if value
            else Path(f"grounded-{timestamp.replace(':', '-')}.json")
        )
        candidate = candidate if candidate.is_absolute() else root / candidate
        candidate = candidate.resolve()
        if root != candidate.parent and root not in candidate.parents:
            raise CommandError("Evaluation output must remain under var/evaluation.")
        return (
            candidate if candidate.suffix == ".json" else candidate.with_suffix(".json")
        )

    @staticmethod
    def _markdown(report: dict[str, Any]) -> str:
        lines = [
            "# Grounded-answer evaluation report",
            "",
            f"- Timestamp: {report['timestamp']}",
            f"- Approved: {report['case_counts']['approved']}",
            f"- Pending: {report['case_counts']['pending']}",
            "",
            "## Metrics",
            "",
        ]
        lines.extend(f"- {key}: {value}" for key, value in report["metrics"].items())
        lines.extend(["", "## Cases", ""])
        for item in report["case_outcomes"]:
            lines.append(
                f"- {item['case_id']}: status={item['final_status']}, "
                f"passed={item['passed']}, failure={item['failure_reason'] or 'none'}, "
                f"unsupported_claim_review={item['unsupported_claim_review_result']}"
            )
        lines.extend(["", f"Review limitation: {report['review_limitation']}", ""])
        return "\n".join(lines)
