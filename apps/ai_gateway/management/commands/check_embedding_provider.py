from django.core.management.base import BaseCommand, CommandError

from apps.ai_gateway.embeddings import EmbeddingError
from apps.knowledge_base.runtime import embedding_provider


class Command(BaseCommand):
    help = "Check the configured local embedding provider and model."

    def handle(self, *args: object, **options: object) -> None:
        try:
            identity = embedding_provider().health_check()
        except (EmbeddingError, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"{identity.stable_identity} dimension={identity.dimension} "
                f"metric={identity.distance_metric}"
            )
        )
