from argparse import ArgumentParser
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.bulk_review import export_review_workbook


class Command(BaseCommand):
    help = "Export current chunks for controlled offline review."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("document_id")
        parser.add_argument(
            "--output",
            help="Destination .xlsx, .csv, or .json path.",
        )

    def handle(self, *args: object, **options: object) -> None:
        document_id = str(options["document_id"])
        output = options.get("output")
        path = (
            Path(str(output))
            if output
            else Path("var") / "exports" / f"{document_id}.chunk-review.xlsx"
        )
        try:
            count = export_review_workbook(document_id, path)
        except ValidationError as exc:
            raise CommandError("; ".join(exc.messages)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Exported {count} current chunks to {path.resolve()}.")
        )
