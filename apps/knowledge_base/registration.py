"""Controlled source-file registration."""

import hashlib
from pathlib import Path

from django.core.files import File
from django.db import transaction

from .exceptions import DuplicateDocumentError
from .models import DocumentVersion, KnowledgeDocument
from .validation import ValidatedDocument, validate_document_file


@transaction.atomic
def register_document_file(
    document: KnowledgeDocument,
    source_path: Path,
) -> tuple[DocumentVersion, bool]:
    validated = validate_document_file(source_path)
    duplicate = DocumentVersion.objects.filter(checksum=validated.checksum).first()
    if duplicate is not None:
        if duplicate.document_id == document.pk:
            return duplicate, False
        raise DuplicateDocumentError(
            f"Identical content is already registered as {duplicate.version_id}."
        )

    version_id = stable_version_id(document, validated)
    version = DocumentVersion(
        version_id=version_id,
        document=document,
        version_or_edition=document.version_or_edition,
        revision_or_effective_date=document.revision_or_effective_date,
        revision_label=document.revision_label,
        source_filename=validated.path.name,
        checksum=validated.checksum,
        file_size=validated.size,
        media_type=validated.media_type,
    )
    with validated.path.open("rb") as source:
        version.source_file.save(validated.path.name, File(source), save=False)
        version.save()

    document.source_filename = validated.path.name
    document.checksum = validated.checksum
    document.processing_status = KnowledgeDocument.ProcessingStatus.NOT_PROCESSED
    document.lifecycle_status = KnowledgeDocument.LifecycleStatus.UNDER_REVIEW
    document.save(
        update_fields=[
            "source_filename",
            "checksum",
            "processing_status",
            "lifecycle_status",
            "updated_at",
        ]
    )
    return version, True


def stable_version_id(
    document: KnowledgeDocument,
    validated: ValidatedDocument,
) -> str:
    edition = document.version_or_edition or "unversioned"
    normalized_edition = "".join(
        character if character.isalnum() else "-" for character in edition
    ).strip("-")
    digest = hashlib.sha256(
        f"{document.document_id}|{edition}|{validated.checksum}".encode()
    ).hexdigest()[:12]
    return f"{document.document_id}-{normalized_edition}-{digest}"
