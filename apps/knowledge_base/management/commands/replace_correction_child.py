from argparse import ArgumentParser
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.knowledge_base.models import DocumentChunk
from apps.knowledge_base.replacements import replace_correction_child

MAX_REPLACEMENT_BYTES = 2 * 1024 * 1024


class Command(BaseCommand):
    help = "Replace one correction child through the audited correction service."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("chunk_id")
        parser.add_argument("--content-file", required=True)
        parser.add_argument("--source-hash", required=True)
        parser.add_argument("--reason", required=True)
        parser.add_argument("--reviewer-notes", required=True)
        parser.add_argument("--reviewer", required=True)
        parser.add_argument("--safety-confirmed", action="store_true")

    def handle(self, *args: object, **options: object) -> None:
        path = Path(str(options["content_file"]))
        if not path.is_file():
            raise CommandError("Replacement content file not found.")
        if path.stat().st_size > MAX_REPLACEMENT_BYTES:
            raise CommandError("Replacement content exceeds the 2 MB limit.")
        try:
            replacement_content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise CommandError("Replacement content must be UTF-8.") from exc
        if "\x00" in replacement_content:
            raise CommandError("Replacement content contains a NUL character.")

        reviewer = (
            get_user_model()
            .objects.filter(
                username=str(options["reviewer"]),
                is_active=True,
                is_staff=True,
            )
            .first()
        )
        if reviewer is None or not (
            reviewer.has_perm("knowledge_base.change_documentchunk")
            and reviewer.has_perm("knowledge_base.add_chunkreplacementcorrection")
        ):
            raise CommandError("Reviewer lacks staff chunk-replacement permissions.")
        try:
            audit = replace_correction_child(
                str(options["chunk_id"]),
                replacement_content,
                expected_source_hash=str(options["source_hash"]),
                reviewer=reviewer,
                reviewer_notes=str(options["reviewer_notes"]),
                reason=str(options["reason"]),
                safety_confirmed=bool(options["safety_confirmed"]),
            )
        except (ValidationError, DocumentChunk.DoesNotExist) as exc:
            message = (
                "; ".join(exc.messages)
                if isinstance(exc, ValidationError)
                else "Correction child not found."
            )
            raise CommandError(message) from exc
        self.stdout.write(
            self.style.SUCCESS(
                f"Replaced {audit.replaced_child_id} with "
                f"{audit.replacement_child_id}; audit={audit.id}."
            )
        )
