import json
from argparse import ArgumentParser
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.evaluation import (
    APPROVED,
    PENDING,
    EvaluationCase,
    calibration,
    evaluate,
    load_dataset,
    render_markdown,
)
from apps.knowledge_base.models import VectorIndexVersion
from apps.knowledge_base.retrieval import RetrievedChunk, retrieve
from apps.knowledge_base.runtime import embedding_provider, vector_store


class Command(BaseCommand):
    help = "Evaluate approved retrieval cases and write JSON/Markdown reports."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument(
            "--dataset",
            default="tests/fixtures/fanuc_retrieval_evaluation.json",
        )
        parser.add_argument("--document")
        parser.add_argument(
            "--retrieval-mode",
            choices=("dense", "safety_first"),
            default="dense",
        )
        parser.add_argument(
            "--top-k", type=int, default=settings.RETRIEVAL_DEFAULT_TOP_K
        )
        parser.add_argument("--threshold", type=float)
        parser.add_argument("--output")
        parser.add_argument("--approved-only", action="store_true")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--calibration-thresholds",
            help="Comma-separated candidate thresholds; no threshold is selected.",
        )

    def handle(self, *args: object, **options: object) -> None:
        typed: dict[str, Any] = options
        dataset_path = Path(typed["dataset"])
        if not dataset_path.is_absolute():
            dataset_path = settings.BASE_DIR / dataset_path
        try:
            metadata, cases, invalid = load_dataset(dataset_path.resolve())
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise CommandError(f"Evaluation dataset is invalid: {exc}") from exc
        approved = [case for case in cases if case.review_status == APPROVED]
        pending = [case for case in cases if case.review_status == PENDING]
        counts = {
            "approved": len(approved),
            "pending": len(pending),
            "invalid": len(invalid),
            "skipped": len(pending),
        }
        self.stdout.write(
            "Cases: approved={approved}, pending={pending}, invalid={invalid}, "
            "skipped={skipped}".format(**counts)
        )
        if typed["dry_run"]:
            self.stdout.write(
                "Dry-run complete; no retrieval or report write occurred."
            )
            return

        index = VectorIndexVersion.objects.filter(
            status=VectorIndexVersion.Status.ACTIVE
        ).first()
        if index is None:
            raise CommandError("No active vector index exists.")
        threshold = (
            typed["threshold"]
            if typed["threshold"] is not None
            else settings.RETRIEVAL_MIN_SCORE
        )
        mode = str(typed["retrieval_mode"])
        top_k = int(typed["top_k"])
        if top_k < 1 or top_k > settings.RETRIEVAL_MAX_TOP_K:
            raise CommandError(
                f"top-k must be between 1 and {settings.RETRIEVAL_MAX_TOP_K}."
            )
        calibration_thresholds = self._thresholds(typed.get("calibration_thresholds"))
        if approved:
            provider = embedding_provider()
            with vector_store() as store:

                def run_case(
                    case: EvaluationCase,
                    case_threshold: float | None,
                    retrieval_mode: str,
                    case_top_k: int,
                    document: str | None,
                ) -> list[RetrievedChunk]:
                    return retrieve(
                        case.question,
                        provider,
                        store,
                        top_k=case_top_k,
                        max_top_k=settings.RETRIEVAL_MAX_TOP_K,
                        minimum_score=case_threshold,
                        safety_first=retrieval_mode == "safety_first",
                        document_id=document,
                    )

                outcomes, metrics = evaluate(
                    approved,
                    run_case,
                    retrieval_mode=mode,
                    threshold=threshold,
                    top_k=top_k,
                    document_id=typed["document"],
                )
                calibration_rows = calibration(
                    approved,
                    run_case,
                    calibration_thresholds,
                    retrieval_mode=mode,
                    top_k=top_k,
                    document_id=typed["document"],
                )
        else:
            outcomes, metrics = evaluate(
                [],
                lambda *args: [],
                retrieval_mode=mode,
                threshold=threshold,
                top_k=top_k,
                document_id=typed["document"],
            )
            calibration_rows = []
        timestamp = datetime.now(UTC).isoformat()
        report = {
            "timestamp": timestamp,
            "dataset": metadata,
            "index": {
                "id": str(index.id),
                "corpus_fingerprint": index.corpus_fingerprint,
                "model_identity": index.model_identity,
                "vector_dimension": index.vector_dimension,
            },
            "retrieval_configuration": {
                "mode": mode,
                "threshold": threshold,
                "top_k": top_k,
                "document_id": typed["document"],
                "approved_only": bool(typed["approved_only"]),
            },
            "case_counts": counts,
            "pending_cases": [case.question_id for case in pending],
            "invalid_cases": invalid,
            "case_outcomes": outcomes,
            "metrics": metrics,
            "threshold_calibration": calibration_rows,
            "threshold_selection": "No production threshold was selected.",
        }
        json_path = self._output_path(typed.get("output"), timestamp)
        markdown_path = json_path.with_suffix(".md")
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )
        markdown_path.write_text(render_markdown(report), encoding="utf-8")
        self.stdout.write(
            self.style.SUCCESS(
                f"Evaluation reports: {json_path.resolve()} and "
                f"{markdown_path.resolve()}"
            )
        )

    @staticmethod
    def _thresholds(value: str | None) -> list[float]:
        if not value:
            return []
        try:
            thresholds = [float(item.strip()) for item in value.split(",")]
        except ValueError as exc:
            raise CommandError("Calibration thresholds must be decimals.") from exc
        if any(not 0 <= threshold <= 1 for threshold in thresholds):
            raise CommandError("Calibration thresholds must be between 0 and 1.")
        return thresholds

    @staticmethod
    def _output_path(value: str | None, timestamp: str) -> Path:
        root = (settings.BASE_DIR / "var" / "evaluation").resolve()
        if value:
            candidate = Path(value)
            candidate = candidate if candidate.is_absolute() else root / candidate
        else:
            safe_timestamp = timestamp.replace(":", "-").replace("+", "_")
            candidate = root / f"retrieval-{safe_timestamp}.json"
        candidate = candidate.resolve()
        if root != candidate.parent and root not in candidate.parents:
            raise CommandError("Evaluation output must remain under var/evaluation.")
        if candidate.suffix.lower() != ".json":
            candidate = candidate.with_suffix(".json")
        return candidate
