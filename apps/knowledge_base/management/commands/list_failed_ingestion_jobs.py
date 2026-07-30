from django.core.management.base import BaseCommand

from apps.knowledge_base.models import IngestionJob


class Command(BaseCommand):
    help = "List failed or manual-review ingestion jobs without stack traces."

    def handle(self, *args: object, **options: object) -> None:
        jobs = IngestionJob.objects.filter(
            status__in=[
                IngestionJob.Status.FAILED,
                IngestionJob.Status.MANUAL_REVIEW,
            ]
        )
        if not jobs.exists():
            self.stdout.write("No failed or manual-review ingestion jobs.")
            return
        for job in jobs:
            messages = [*job.errors, *job.warnings]
            self.stdout.write(f"{job.id}\t{job.document_id}\t{job.status}\t{messages}")
