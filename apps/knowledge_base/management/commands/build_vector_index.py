from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.indexing import build_index, eligible_chunks
from apps.knowledge_base.runtime import embedding_provider, vector_store


class Command(BaseCommand):
    help = "Preview or build and atomically activate a versioned vector index."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--document")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        typed: dict[str, Any] = options
        chunks = eligible_chunks()
        if typed["document"]:
            chunks = chunks.filter(document_id=typed["document"])
        count = chunks.count()
        if typed["dry_run"]:
            self.stdout.write(f"Eligible chunks: {count}; no changes made.")
            return
        try:
            with vector_store() as store:
                index = build_index(
                    embedding_provider(),
                    store,
                    document_id=typed["document"],
                )
        except Exception as exc:
            raise CommandError(
                f"Index build failed safely: {type(exc).__name__}"
            ) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Activated {index.id}; collection={index.collection_name}; "
                f"indexed={index.indexed_chunk_count}"
            )
        )
