from argparse import ArgumentParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.metadata import import_metadata, load_metadata


class Command(BaseCommand):
    help = "Import controlled document metadata from a YAML file."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("metadata_path")

    def handle(self, *args: object, **options: object) -> None:
        try:
            metadata = load_metadata(Path(str(options["metadata_path"])))
            document, created = import_metadata(metadata)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} metadata for {document.document_id}; status is under review."
            )
        )
