import json
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.bulk_review import (
    apply_review_plans,
    dry_run_report,
    load_review_rows,
    report_digest,
    resolve_reviewer,
    validate_review_rows,
)


class Command(BaseCommand):
    help = "Validate or atomically apply a controlled chunk-review workbook."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("review_file")
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--dry-run", action="store_true")
        mode.add_argument("--apply", action="store_true")
        parser.add_argument(
            "--reviewer",
            help="Staff username recorded in the correction audit.",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help="Explicitly confirm apply when no matching dry-run report exists.",
        )
        parser.add_argument(
            "--report",
            help="Override the JSON report path.",
        )

    def handle(self, *args: object, **options: object) -> None:
        path = Path(str(options["review_file"]))
        report_path = (
            Path(str(options["report"]))
            if options.get("report")
            else path.with_suffix(
                ".apply-report.json" if options["apply"] else ".dry-run.json"
            )
        )
        try:
            reviewer = resolve_reviewer(
                str(options["reviewer"]) if options.get("reviewer") else None
            )
            rows = load_review_rows(path)
            plans = validate_review_rows(rows)
        except (ValidationError, OSError, ValueError, json.JSONDecodeError) as exc:
            message = (
                "; ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else str(exc)
            )
            raise CommandError(message) from exc

        report = dry_run_report(path, plans)
        report["reviewer"] = reviewer.get_username()
        report_path.parent.mkdir(parents=True, exist_ok=True)

        if options["dry_run"]:
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._print_validation(report)
            if not report["valid"]:
                raise CommandError(
                    f"Dry-run failed. Report written to {report_path.resolve()}."
                )
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry-run passed. Report written to {report_path.resolve()}."
                )
            )
            return

        self.stdout.write(
            self.style.WARNING(
                "BACKUP REMINDER: copy the configured SQLite database before apply."
            )
        )
        dry_report_path = path.with_suffix(".dry-run.json")
        has_matching_report = self._matching_dry_run(dry_report_path, path)
        if not has_matching_report and not options["confirm"]:
            raise CommandError(
                "Apply requires a successful matching dry-run report or --confirm."
            )
        if not report["valid"]:
            report["applied"] = False
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            self._print_validation(report)
            raise CommandError("Apply blocked because validation failed.")

        try:
            results = apply_review_plans(plans, reviewer)
        except Exception as exc:
            report["applied"] = False
            report["application_error"] = str(exc)
            report_path.write_text(
                json.dumps(report, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            raise CommandError(
                "The transaction was rolled back; no review changes were applied."
            ) from exc
        report["applied"] = True
        report["results"] = results
        report_path.write_text(
            json.dumps(report, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"Applied {len(results)} review rows atomically. "
                f"Report: {report_path.resolve()}."
            )
        )

    def _matching_dry_run(self, report_path: Path, source: Path) -> bool:
        try:
            payload: dict[str, Any] = json.loads(
                report_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            return False
        return bool(
            payload.get("valid")
            and payload.get("source_sha256") == report_digest(source)
        )

    def _print_validation(self, report: dict[str, Any]) -> None:
        for row in report["rows"]:
            if row["errors"]:
                self.stderr.write(
                    f"Row {row['row']} [{row['chunk_id']}]: " + "; ".join(row["errors"])
                )
            else:
                self.stdout.write(
                    f"Row {row['row']} [{row['chunk_id']}]: {row['planned_change']}"
                )
