from django.core.management.base import BaseCommand

from apps.knowledge_base.models import VectorIndexVersion


class Command(BaseCommand):
    help = "Show active vector-index metadata."

    def handle(self, *args: object, **options: object) -> None:
        index = VectorIndexVersion.objects.filter(
            status=VectorIndexVersion.Status.ACTIVE
        ).first()
        if index is None:
            self.stdout.write("No active vector index.")
            return
        self.stdout.write(
            f"id={index.id} collection={index.collection_name} "
            f"model={index.model_identity} dimension={index.vector_dimension} "
            f"fingerprint={index.corpus_fingerprint} "
            f"vectors={index.indexed_chunk_count}"
        )
