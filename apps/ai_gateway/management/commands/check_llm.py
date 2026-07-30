from django.core.management.base import BaseCommand, CommandError

from apps.ai_gateway.errors import LLMGatewayError
from apps.ai_gateway.gateway import get_text_gateway


class Command(BaseCommand):
    help = "Verify the configured local LLM provider and text model."

    def handle(self, *args: object, **options: object) -> None:
        try:
            health = get_text_gateway().health_check()
        except LLMGatewayError as exc:
            raise CommandError(
                f"Local LLM check failed ({exc.code}). See README troubleshooting."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Local LLM ready: provider={health.provider}, model={health.model}"
            )
        )
