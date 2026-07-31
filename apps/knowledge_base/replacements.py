"""Controlled replacement of reviewed correction-child content."""

import hashlib
import re
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .chunking import approximate_token_count
from .corrections import content_hash
from .models import ChunkReplacementCorrection, DocumentChunk


def _replacement_id(replaced_child_id: str, new_hash: str) -> str:
    material = f"{replaced_child_id}|{new_hash}".encode()
    return "CHK-R-" + hashlib.sha256(material).hexdigest()[:30]


def _safety_content(chunk: DocumentChunk, replacement_content: str) -> bool:
    return bool(
        chunk.contains_warning
        or chunk.contains_caution
        or re.search(r"\b(?:warning|caution)\b", chunk.content, re.IGNORECASE)
        or re.search(
            r"\b(?:warning|caution)\b",
            replacement_content,
            re.IGNORECASE,
        )
    )


def validate_replacement(
    child: DocumentChunk,
    replacement_content: str,
    *,
    expected_source_hash: str,
    reviewer_notes: str,
    reason: str,
    safety_confirmed: bool,
) -> str:
    if child.origin not in {
        DocumentChunk.Origin.CORRECTION,
        DocumentChunk.Origin.CORRECTION_REPLACEMENT,
    }:
        raise ValidationError("Only a correction child can be replaced.")
    if (
        not child.is_current_generation
        or child.review_status == DocumentChunk.ReviewStatus.SUPERSEDED
    ):
        raise ValidationError("The correction child is already superseded or stale.")
    if child.content_hash != expected_source_hash:
        raise ValidationError("Source content hash mismatch.")
    if not replacement_content.strip():
        raise ValidationError("Replacement content cannot be empty.")
    new_hash = content_hash(replacement_content)
    if new_hash == child.content_hash:
        raise ValidationError("Replacement content must differ from the source.")
    if not reviewer_notes.strip():
        raise ValidationError("Reviewer notes are required.")
    if not reason.strip():
        raise ValidationError("A replacement reason is required.")
    if child.parent_chunk is None:
        raise ValidationError("Correction-child source provenance is missing.")
    parent = child.parent_chunk
    if (
        child.page_start is None
        or child.page_end is None
        or parent.page_start is None
        or parent.page_end is None
        or child.page_start < parent.page_start
        or child.page_end > parent.page_end
        or child.page_start > child.page_end
    ):
        raise ValidationError("Child page range is outside its source chunk.")
    if _safety_content(child, replacement_content) and not safety_confirmed:
        raise ValidationError(
            "Safety confirmation is required for warning/caution content."
        )
    duplicate = (
        DocumentChunk.objects.filter(
            document_version=child.document_version,
            content_hash=new_hash,
            retrieval_enabled=True,
            is_current_generation=True,
        )
        .exclude(pk=child.pk)
        .exists()
    )
    if duplicate:
        raise ValidationError("Replacement duplicates retrieval-active content.")
    return new_hash


def _materialize_replacement(
    replaced: DocumentChunk,
    corrected_content: str,
    *,
    reviewer: Any,
    reviewer_notes: str,
    new_hash: str,
) -> DocumentChunk:
    now = timezone.now()
    replacement_id = _replacement_id(replaced.chunk_id, new_hash)
    replaced.review_status = DocumentChunk.ReviewStatus.SUPERSEDED
    replaced.retrieval_enabled = False
    replaced.is_current_generation = False
    replaced.reviewed_by = reviewer
    replaced.reviewed_at = now
    replaced.save(
        update_fields=[
            "review_status",
            "retrieval_enabled",
            "is_current_generation",
            "reviewed_by",
            "reviewed_at",
        ]
    )
    replacement, _ = DocumentChunk.objects.update_or_create(
        chunk_id=replacement_id,
        defaults={
            "document": replaced.document,
            "document_version": replaced.document_version,
            "sequence": replaced.sequence,
            "content": corrected_content,
            "content_hash": new_hash,
            "chapter": replaced.chapter,
            "section": replaced.section,
            "page_start": replaced.page_start,
            "page_end": replaced.page_end,
            "manufacturer": replaced.manufacturer,
            "equipment_family": replaced.equipment_family,
            "equipment_model": replaced.equipment_model,
            "subsystem": replaced.subsystem,
            "safety_priority": replaced.safety_priority,
            "access_level": replaced.access_level,
            "token_count": approximate_token_count(corrected_content),
            "contains_warning": (
                replaced.contains_warning
                or bool(re.search(r"\bwarning\b", corrected_content, re.IGNORECASE))
            ),
            "contains_caution": (
                replaced.contains_caution
                or bool(re.search(r"\bcaution\b", corrected_content, re.IGNORECASE))
            ),
            "review_status": DocumentChunk.ReviewStatus.APPROVED,
            "processing_warnings": [],
            "origin": DocumentChunk.Origin.CORRECTION_REPLACEMENT,
            "parent_chunk": replaced.parent_chunk,
            "retrieval_enabled": True,
            "is_current_generation": True,
            "reviewer_notes": reviewer_notes.strip(),
            "reviewed_by": reviewer,
            "reviewed_at": now,
        },
    )
    return replacement


@transaction.atomic
def replace_correction_child(
    child_id: str,
    replacement_content: str,
    *,
    expected_source_hash: str,
    reviewer: Any,
    reviewer_notes: str,
    reason: str,
    safety_confirmed: bool,
) -> ChunkReplacementCorrection:
    child = (
        DocumentChunk.objects.select_for_update()
        .select_related(
            "document",
            "document_version",
            "parent_chunk",
        )
        .get(pk=child_id)
    )
    new_hash = validate_replacement(
        child,
        replacement_content,
        expected_source_hash=expected_source_hash,
        reviewer_notes=reviewer_notes,
        reason=reason,
        safety_confirmed=safety_confirmed,
    )
    replacement = _materialize_replacement(
        child,
        replacement_content,
        reviewer=reviewer,
        reviewer_notes=reviewer_notes,
        new_hash=new_hash,
    )
    return ChunkReplacementCorrection.objects.create(
        replaced_child=child,
        replacement_child=replacement,
        old_content_hash=child.content_hash,
        new_content_hash=new_hash,
        corrected_content=replacement_content,
        reason=reason.strip(),
        reviewer_notes=reviewer_notes.strip(),
        reviewer=reviewer,
        document=child.document,
        document_version=child.document_version,
        status=ChunkReplacementCorrection.Status.APPLIED,
        applied_at=timezone.now(),
    )


@transaction.atomic
def reapply_replacements(document_version_id: str) -> None:
    audits = ChunkReplacementCorrection.objects.filter(
        document_version_id=document_version_id
    ).select_related("replaced_child", "reviewer")
    for audit in audits.order_by("created_at"):
        candidates = DocumentChunk.objects.filter(
            document_version_id=document_version_id,
            chunk_id=audit.replaced_child_id,
            content_hash=audit.old_content_hash,
            is_current_generation=True,
        )
        if candidates.count() != 1:
            audit.status = ChunkReplacementCorrection.Status.STALE
            audit.applied_at = None
            audit.save(update_fields=["status", "applied_at"])
            DocumentChunk.objects.filter(pk=audit.replacement_child_id).update(
                retrieval_enabled=False,
                is_current_generation=False,
            )
            continue
        replaced = candidates.get()
        replacement = _materialize_replacement(
            replaced,
            audit.corrected_content,
            reviewer=audit.reviewer,
            reviewer_notes=audit.reviewer_notes,
            new_hash=audit.new_content_hash,
        )
        audit.replaced_child = replaced
        audit.replacement_child = replacement
        audit.status = ChunkReplacementCorrection.Status.APPLIED
        audit.applied_at = timezone.now()
        audit.save(
            update_fields=[
                "replaced_child",
                "replacement_child",
                "status",
                "applied_at",
            ]
        )
