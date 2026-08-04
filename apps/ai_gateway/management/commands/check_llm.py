from django.core.management.base import BaseCommand, CommandError

from apps.ai_gateway.errors import LLMGatewayError
from apps.ai_gateway.gateway import get_text_gateway


class Command(BaseCommand):
    help = "Verify the configured generation provider and text model."

    def handle(self, *args: object, **options: object) -> None:
        try:
            health = get_text_gateway().health_check()
        except LLMGatewayError as exc:
            raise CommandError(
                f"Generation provider check failed ({exc.code}). "
                "See README troubleshooting."
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Local LLM ready: provider={health.provider}, "
                f"model={health.model}, latency_ms={health.duration_ms:.1f}, "
                f"input_tokens={health.input_tokens}, "
                f"output_tokens={health.output_tokens}, "
                f"total_tokens={health.total_tokens}"
            )
        )
