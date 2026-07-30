from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.exceptions import KnowledgeBaseError
from apps.knowledge_base.ingestion import process_document


class Command(BaseCommand):
    help = "Replace generated chunks for one previously approved document."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("document_id")

    def handle(self, *args: object, **options: object) -> None:
        try:
            job = process_document(str(options["document_id"]), reprocess=True)
        except KnowledgeBaseError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Reprocessing job {job.id} finished with status={job.status}; "
                f"chunks={job.chunk_count}; warnings={len(job.warnings)}."
            )
        )
