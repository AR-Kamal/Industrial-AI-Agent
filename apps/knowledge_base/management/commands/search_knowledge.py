import json
from argparse import ArgumentParser
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.retrieval import retrieve
from apps.knowledge_base.runtime import embedding_provider, vector_store


class Command(BaseCommand):
    help = "Search the active index and print validated provenance; no LLM is called."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("query")
        parser.add_argument(
            "--top-k", type=int, default=settings.RETRIEVAL_DEFAULT_TOP_K
        )
        parser.add_argument("--document")
        parser.add_argument("--safety-first", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        typed: dict[str, Any] = options
        try:
            with vector_store() as store:
                results = retrieve(
                    typed["query"],
                    embedding_provider(),
                    store,
                    top_k=typed["top_k"],
                    max_top_k=settings.RETRIEVAL_MAX_TOP_K,
                    minimum_score=settings.RETRIEVAL_MIN_SCORE,
                    safety_first=typed["safety_first"],
                    document_id=typed["document"],
                )
        except Exception as exc:
            raise CommandError(f"Search failed safely: {type(exc).__name__}") from exc
        self.stdout.write(json.dumps([result.__dict__ for result in results], indent=2))
