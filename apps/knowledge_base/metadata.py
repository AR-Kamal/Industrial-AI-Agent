"""Strict metadata import for controlled knowledge sources."""

from datetime import date
from pathlib import Path
from typing import Any

import yaml
from django.db import transaction

from .models import KnowledgeDocument

REQUIRED_METADATA_FIELDS = {
    "document_id",
    "title",
    "document_code",
    "manufacturer",
    "document_type",
    "language",
    "safety_priority",
    "access_level",
}


def load_metadata(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as source:
        loaded = yaml.safe_load(source)
    if not isinstance(loaded, dict):
        raise ValueError("Metadata YAML must contain a mapping.")
    missing = sorted(REQUIRED_METADATA_FIELDS - loaded.keys())
    if missing:
        raise ValueError(f"Missing required metadata fields: {', '.join(missing)}")
    return loaded


@transaction.atomic
def import_metadata(
    metadata: dict[str, Any],
) -> tuple[KnowledgeDocument, bool]:
    revision_label = str(
        metadata.get("revision_date") or metadata.get("effective_date") or ""
    ).strip()
    defaults = {
        "title": str(metadata["title"]).strip(),
        "document_code": str(metadata["document_code"]).strip(),
        "document_type": str(metadata["document_type"]).strip(),
        "manufacturer": str(metadata["manufacturer"]).strip(),
        "equipment_family": str(metadata.get("equipment_family", "")).strip(),
        "equipment_model": str(metadata.get("equipment_model", "")).strip(),
        "subsystem": str(metadata.get("subsystem", "")).strip(),
        "version_or_edition": str(
            metadata.get("version") or metadata.get("edition") or ""
        ).strip(),
        "revision_or_effective_date": parse_partial_date(revision_label),
        "revision_label": revision_label,
        "language": str(metadata["language"]).strip(),
        "approval_status": KnowledgeDocument.ApprovalStatus.PENDING,
        "lifecycle_status": KnowledgeDocument.LifecycleStatus.UNDER_REVIEW,
        "current_version_verification_status": map_verification_status(
            str(metadata.get("current_status", ""))
        ),
        "access_level": str(metadata["access_level"]).strip(),
        "safety_priority": str(metadata["safety_priority"]).strip(),
        "notes": str(metadata.get("notes", "")).strip(),
    }
    return KnowledgeDocument.objects.update_or_create(
        document_id=str(metadata["document_id"]).strip(),
        defaults=defaults,
    )


def parse_partial_date(value: str) -> date | None:
    if not value:
        return None
    for format_length in (10, 7, 4):
        if len(value) == format_length:
            parts = [int(part) for part in value.split("-")]
            if len(parts) == 3:
                return date(parts[0], parts[1], parts[2])
            if len(parts) == 2:
                return date(parts[0], parts[1], 1)
            return date(parts[0], 1, 1)
    raise ValueError("Revision date must use YYYY, YYYY-MM, or YYYY-MM-DD.")


def map_verification_status(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {
        "requires_version_verification",
        "requires_current_version_verification",
    }:
        return KnowledgeDocument.VerificationStatus.REQUIRES_VERIFICATION
    if normalized in {"verified", "verified_current", "current"}:
        return KnowledgeDocument.VerificationStatus.VERIFIED_CURRENT
    return KnowledgeDocument.VerificationStatus.UNVERIFIED


def validate_metadata(document: KnowledgeDocument) -> list[str]:
    errors: list[str] = []
    for field_name in (
        "document_id",
        "title",
        "document_code",
        "document_type",
        "manufacturer",
        "language",
        "access_level",
        "safety_priority",
    ):
        if not getattr(document, field_name):
            errors.append(f"{field_name} is required.")
    if (
        document.safety_priority == KnowledgeDocument.SafetyPriority.CRITICAL
        and document.current_version_verification_status
        == KnowledgeDocument.VerificationStatus.UNVERIFIED
    ):
        errors.append(
            "Critical safety documents must record current-version verification status."
        )
    if document.approval_status == KnowledgeDocument.ApprovalStatus.APPROVED:
        if document.approved_by_id is None:
            errors.append("Approved documents must identify approved_by.")
    if not document.versions.exists():
        errors.append("At least one document version must be registered.")
    return errors
