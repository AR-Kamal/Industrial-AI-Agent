from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.knowledge_base.models import VectorIndexVersion


class Command(BaseCommand):
    help = "Retire an index metadata record after explicit confirmation."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("index_id")
        parser.add_argument("--confirm", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        typed: dict[str, Any] = options
        try:
            index = VectorIndexVersion.objects.get(pk=typed["index_id"])
        except (VectorIndexVersion.DoesNotExist, ValueError) as exc:
            raise CommandError("Vector index was not found.") from exc
        self.stdout.write(f"Affected indexes: 1 ({index.id}, {index.status})")
        if typed["dry_run"]:
            return
        if not typed["confirm"]:
            raise CommandError("Pass --confirm to retire this index.")
        index.status = VectorIndexVersion.Status.RETIRED
        index.retired_at = timezone.now()
        index.save(update_fields=["status", "retired_at"])
