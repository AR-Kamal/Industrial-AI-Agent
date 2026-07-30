"""Auditable, reproducible corrections to generated document chunks."""

import hashlib
import re
import uuid
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .chunking import approximate_token_count, normalize_chunk_text
from .models import ChunkSplitCorrection, DocumentChunk

SPLIT_MARKER = "--- SPLIT ---"
SAFETY_BOUNDARY_PATTERN = re.compile(
    r"\b(?:warning|caution|prerequisite|exception|note|table)\b"
    r"|(?:^|\n)\s*(?:\(?\d+\)?[.)]|[a-z][.)])\s+",
    re.IGNORECASE,
)
SEQUENCE_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True)
class SplitSegment:
    content: str
    chapter: str
    section: str
    page_start: int | None
    page_end: int | None
    contains_warning: bool
    contains_caution: bool
    retrieval_enabled: bool
    reviewer_notes: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "content": self.content,
            "chapter": self.chapter,
            "section": self.section,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "contains_warning": self.contains_warning,
            "contains_caution": self.contains_caution,
            "retrieval_enabled": self.retrieval_enabled,
            "reviewer_notes": self.reviewer_notes,
        }


def split_marker_parts(marked_content: str) -> list[str]:
    """Split marked source text without accepting empty children."""
    parts = [part.strip() for part in marked_content.split(SPLIT_MARKER)]
    if len(parts) < 2:
        raise ValidationError(f"Insert at least one {SPLIT_MARKER} marker.")
    if any(not part for part in parts):
        raise ValidationError("Split points cannot create an empty child chunk.")
    return parts


def boundary_requires_confirmation(marked_content: str) -> bool:
    """Return true when a split is close to safety- or procedure-shaped text."""
    offset = 0
    for part in marked_content.split(SPLIT_MARKER)[:-1]:
        offset += len(part)
        window_start = max(0, offset - 300)
        window_end = min(len(marked_content), offset + 300)
        if SAFETY_BOUNDARY_PATTERN.search(marked_content[window_start:window_end]):
            return True
        offset += len(SPLIT_MARKER)
    return False


def content_hash(content: str) -> str:
    return hashlib.sha256(normalize_chunk_text(content).encode("utf-8")).hexdigest()


def validate_segments(
    source: DocumentChunk,
    segments: list[SplitSegment],
    *,
    safety_confirmed: bool,
    safety_confirmation_required: bool,
    artifact_note: str,
) -> None:
    if len(segments) < 2:
        raise ValidationError("A split must create at least two child chunks.")
    if any(not segment.content.strip() for segment in segments):
        raise ValidationError("Child chunks cannot be empty.")
    source_is_safety_sensitive = bool(SAFETY_BOUNDARY_PATTERN.search(source.content))
    if (
        safety_confirmation_required or source_is_safety_sensitive
    ) and not safety_confirmed:
        raise ValidationError(
            "Confirm that safety statements and procedures remain correctly attached."
        )

    source_start = source.page_start
    source_end = source.page_end
    for segment in segments:
        if re.search(r"\bwarning\b", segment.content, re.IGNORECASE) and not (
            segment.contains_warning
        ):
            raise ValidationError(
                "A child containing WARNING text must keep its warning flag."
            )
        if re.search(r"\bcaution\b", segment.content, re.IGNORECASE) and not (
            segment.contains_caution
        ):
            raise ValidationError(
                "A child containing CAUTION text must keep its caution flag."
            )
        if (segment.page_start is None) != (segment.page_end is None):
            raise ValidationError("Each child must have both page values or neither.")
        if segment.page_start is not None and segment.page_end is not None:
            if segment.page_start > segment.page_end:
                raise ValidationError("A child page start cannot exceed its page end.")
            if (
                source_start is None
                or source_end is None
                or segment.page_start < source_start
                or segment.page_end > source_end
            ):
                raise ValidationError(
                    "Child page ranges must remain inside the source chunk."
                )

    reconstructed = normalize_chunk_text("\n\n".join(s.content for s in segments))
    if (
        reconstructed != normalize_chunk_text(source.content)
        and not artifact_note.strip()
    ):
        raise ValidationError(
            "Describe every removed or corrected extraction artifact."
        )

    active_hashes = [
        content_hash(segment.content)
        for segment in segments
        if segment.retrieval_enabled
    ]
    if len(active_hashes) != len(set(active_hashes)):
        raise ValidationError("Duplicate child content cannot be retrieval-active.")
    if (
        DocumentChunk.objects.filter(
            document_version=source.document_version,
            content_hash__in=active_hashes,
            retrieval_enabled=True,
            is_current_generation=True,
        )
        .exclude(pk=source.pk)
        .exists()
    ):
        raise ValidationError(
            "Child content duplicates another retrieval-active chunk."
        )


def _child_sequences(source: DocumentChunk, count: int) -> list[Decimal]:
    next_chunk = (
        DocumentChunk.objects.filter(
            document_version=source.document_version,
            is_current_generation=True,
            sequence__gt=source.sequence,
        )
        .order_by("sequence")
        .first()
    )
    upper = next_chunk.sequence if next_chunk else source.sequence + Decimal("1")
    space = upper - source.sequence
    step = (space / Decimal(count + 1)).quantize(
        SEQUENCE_QUANTUM,
        rounding=ROUND_DOWN,
    )
    if step < SEQUENCE_QUANTUM:
        raise ValidationError("There is no safe sequence space for these child chunks.")
    return [source.sequence + (step * index) for index in range(1, count + 1)]


def _stable_child_id(
    correction_id: uuid.UUID,
    ordinal: int,
    child_content_hash: str,
) -> str:
    material = f"{correction_id}|{ordinal}|{child_content_hash}".encode()
    return "CHK-C-" + hashlib.sha256(material).hexdigest()[:30]


@transaction.atomic
def apply_split(
    source: DocumentChunk,
    segments: list[SplitSegment],
    *,
    reviewer: Any,
    artifact_note: str,
    safety_confirmed: bool,
    safety_confirmation_required: bool,
) -> ChunkSplitCorrection:
    """Create an immutable correction recipe and its current child chunks."""
    source = DocumentChunk.objects.select_for_update().get(pk=source.pk)
    if source.origin != DocumentChunk.Origin.GENERATED:
        raise ValidationError("Only a generated chunk can be split.")
    if not source.is_current_generation:
        raise ValidationError("Only a current generated chunk can be split.")
    if source.review_status == DocumentChunk.ReviewStatus.SUPERSEDED:
        raise ValidationError("This chunk has already been superseded.")
    if source.split_corrections.filter(
        status=ChunkSplitCorrection.Status.APPLIED
    ).exists():
        raise ValidationError("This chunk already has an applied split correction.")

    validate_segments(
        source,
        segments,
        safety_confirmed=safety_confirmed,
        safety_confirmation_required=safety_confirmation_required,
        artifact_note=artifact_note,
    )
    correction = ChunkSplitCorrection.objects.create(
        source_chunk=source,
        source_content_hash=source.content_hash,
        document_version=source.document_version,
        segment_payload=[segment.as_dict() for segment in segments],
        artifact_changes=(
            [{"description": artifact_note.strip()}] if artifact_note.strip() else []
        ),
        status=ChunkSplitCorrection.Status.APPLIED,
        created_by=reviewer,
        applied_at=timezone.now(),
    )
    _materialize_children(correction, source, reviewer=reviewer)
    return correction


def _materialize_children(
    correction: ChunkSplitCorrection,
    source: DocumentChunk,
    *,
    reviewer: Any,
) -> list[DocumentChunk]:
    payload = correction.segment_payload
    sequences = _child_sequences(source, len(payload))
    children: list[DocumentChunk] = []
    now = timezone.now()
    for ordinal, (item, sequence) in enumerate(zip(payload, sequences, strict=True), 1):
        child_hash = content_hash(item["content"])
        child_id = _stable_child_id(correction.id, ordinal, child_hash)
        child, _ = DocumentChunk.objects.update_or_create(
            chunk_id=child_id,
            defaults={
                "document": source.document,
                "document_version": source.document_version,
                "sequence": sequence,
                "content": item["content"].strip(),
                "content_hash": child_hash,
                "chapter": item["chapter"],
                "section": item["section"],
                "page_start": item["page_start"],
                "page_end": item["page_end"],
                "manufacturer": source.manufacturer,
                "equipment_family": source.equipment_family,
                "equipment_model": source.equipment_model,
                "subsystem": source.subsystem,
                "safety_priority": source.safety_priority,
                "access_level": source.access_level,
                "token_count": approximate_token_count(item["content"]),
                "contains_warning": item["contains_warning"],
                "contains_caution": item["contains_caution"],
                "review_status": DocumentChunk.ReviewStatus.APPROVED,
                "processing_warnings": [],
                "origin": DocumentChunk.Origin.CORRECTION,
                "parent_chunk": source,
                "retrieval_enabled": item["retrieval_enabled"],
                "is_current_generation": True,
                "reviewer_notes": item["reviewer_notes"],
                "reviewed_by": reviewer,
                "reviewed_at": now,
            },
        )
        children.append(child)

    source.review_status = DocumentChunk.ReviewStatus.SUPERSEDED
    source.retrieval_enabled = False
    audit_note = f"Superseded by split correction {correction.id}."
    source.reviewer_notes = "\n".join(
        note for note in (source.reviewer_notes.strip(), audit_note) if note
    )
    source.reviewed_by = reviewer
    source.reviewed_at = now
    source.save(
        update_fields=[
            "review_status",
            "retrieval_enabled",
            "reviewer_notes",
            "reviewed_by",
            "reviewed_at",
        ]
    )
    return children


@transaction.atomic
def reapply_corrections(document_version_id: str) -> None:
    """Reapply exact-hash corrections and fail closed when source text changed."""
    corrections = ChunkSplitCorrection.objects.select_related("source_chunk").filter(
        document_version_id=document_version_id
    )
    for correction in corrections:
        matches = DocumentChunk.objects.filter(
            document_version_id=document_version_id,
            origin=DocumentChunk.Origin.GENERATED,
            is_current_generation=True,
            content_hash=correction.source_content_hash,
        )
        if matches.count() != 1:
            correction.status = ChunkSplitCorrection.Status.STALE
            correction.applied_at = None
            correction.save(update_fields=["status", "applied_at"])
            DocumentChunk.objects.filter(parent_chunk=correction.source_chunk).update(
                retrieval_enabled=False, is_current_generation=False
            )
            continue
        source = matches.get()

        correction.source_chunk = source
        correction.status = ChunkSplitCorrection.Status.APPLIED
        correction.applied_at = timezone.now()
        correction.save(update_fields=["source_chunk", "status", "applied_at"])
        DocumentChunk.objects.filter(parent_chunk=source).update(
            retrieval_enabled=False,
            is_current_generation=False,
        )
        _materialize_children(correction, source, reviewer=correction.created_by)
