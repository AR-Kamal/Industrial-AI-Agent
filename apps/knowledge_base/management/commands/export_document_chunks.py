import json
from argparse import ArgumentParser
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.models import DocumentChunk, KnowledgeDocument


class Command(BaseCommand):
    help = "Export generated document chunks to local JSON for inspection."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("document_id")
        parser.add_argument("--output", required=True)

    def handle(self, *args: object, **options: object) -> None:
        document_id = str(options["document_id"])
        if not KnowledgeDocument.objects.filter(pk=document_id).exists():
            raise CommandError("Knowledge document not found.")
        chunks = DocumentChunk.objects.filter(document_id=document_id)
        payload = {
            "document_id": document_id,
            "chunk_count": chunks.count(),
            "chunks": [
                {
                    "chunk_id": chunk.chunk_id,
                    "sequence": str(chunk.sequence),
                    "document_version": chunk.document_version_id,
                    "chapter": chunk.chapter,
                    "section": chunk.section,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "manufacturer": chunk.manufacturer,
                    "equipment_family": chunk.equipment_family,
                    "subsystem": chunk.subsystem,
                    "safety_priority": chunk.safety_priority,
                    "token_count": chunk.token_count,
                    "contains_warning": chunk.contains_warning,
                    "contains_caution": chunk.contains_caution,
                    "review_status": chunk.review_status,
                    "content_hash": chunk.content_hash,
                    "processing_warnings": chunk.processing_warnings,
                    "content": chunk.content,
                }
                for chunk in chunks
            ],
        }
        output = Path(str(options["output"])).resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        self.stdout.write(
            self.style.SUCCESS(f"Exported {chunks.count()} chunks to {output}.")
        )
