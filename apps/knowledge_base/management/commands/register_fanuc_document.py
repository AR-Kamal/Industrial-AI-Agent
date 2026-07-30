from argparse import ArgumentParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.exceptions import KnowledgeBaseError
from apps.knowledge_base.metadata import import_metadata, load_metadata
from apps.knowledge_base.registration import register_document_file

DEFAULT_PDF = Path("data/incoming/FANUC_B-80687EN_12_Safety_Handbook.pdf")
DEFAULT_METADATA = Path(
    "data/incoming/FANUC_B-80687EN_12_Safety_Handbook.metadata.yaml"
)


class Command(BaseCommand):
    help = "Register the controlled FANUC safety handbook and metadata."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--pdf", default=str(DEFAULT_PDF))
        parser.add_argument("--metadata", default=str(DEFAULT_METADATA))

    def handle(self, *args: object, **options: object) -> None:
        try:
            metadata = load_metadata(Path(str(options["metadata"])))
            document, _ = import_metadata(metadata)
            version, created = register_document_file(
                document,
                Path(str(options["pdf"])),
            )
        except (OSError, ValueError, KnowledgeBaseError) as exc:
            raise CommandError(str(exc)) from exc

        action = "Registered" if created else "Already registered"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action}: {version.version_id}. "
                "Review and approve it in Django admin before processing."
            )
        )
