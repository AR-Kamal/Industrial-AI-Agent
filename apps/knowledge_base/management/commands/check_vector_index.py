from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.indexing import eligible_chunks
from apps.knowledge_base.models import VectorIndexVersion
from apps.knowledge_base.runtime import vector_store


class Command(BaseCommand):
    help = "Check active index counts, source hashes, and eligibility consistency."

    def handle(self, *args: object, **options: object) -> None:
        index = VectorIndexVersion.objects.filter(
            status=VectorIndexVersion.Status.ACTIVE
        ).first()
        if index is None:
            raise CommandError("No active vector index.")
        records = index.embedding_records.select_related("chunk")
        eligible_ids = set(eligible_chunks().values_list("chunk_id", flat=True))
        record_ids = set(records.values_list("chunk_id", flat=True))
        stale = sum(
            record.source_content_hash != record.chunk.content_hash
            for record in records
        )
        missing = len(eligible_ids - record_ids)
        ineligible = len(record_ids - eligible_ids)
        with vector_store() as store:
            vectors = store.count(index.collection_name)
        orphan = max(0, vectors - records.count())
        self.stdout.write(
            f"eligible={len(eligible_ids)} records={records.count()} vectors={vectors} "
            f"missing={missing} orphan={orphan} ineligible={ineligible} stale={stale}"
        )
        if any((missing, orphan, ineligible, stale)):
            raise CommandError("Active index is inconsistent.")
