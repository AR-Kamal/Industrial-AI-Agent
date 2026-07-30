from argparse import ArgumentParser

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.metadata import validate_metadata
from apps.knowledge_base.models import KnowledgeDocument


class Command(BaseCommand):
    help = "Validate registered document metadata and approval accountability."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("document_id", nargs="?")

    def handle(self, *args: object, **options: object) -> None:
        document_id = options.get("document_id")
        documents = KnowledgeDocument.objects.all()
        if document_id:
            documents = documents.filter(pk=document_id)
        if not documents.exists():
            raise CommandError("No matching knowledge document was found.")

        invalid = 0
        for document in documents:
            errors = validate_metadata(document)
            if errors:
                invalid += 1
                self.stderr.write(f"{document.pk}: {'; '.join(errors)}")
            else:
                self.stdout.write(self.style.SUCCESS(f"{document.pk}: valid"))
        if invalid:
            raise CommandError(f"{invalid} document(s) have metadata errors.")
