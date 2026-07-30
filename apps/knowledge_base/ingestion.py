"""Approved-document extraction and chunk persistence."""

import logging
from dataclasses import asdict
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .chunking import ChunkDraft, ChunkingConfig, DocumentChunker
from .corrections import reapply_corrections
from .exceptions import (
    ExtractionError,
    ManualReviewRequired,
    UnapprovedDocumentError,
)
from .extraction import ExtractionResult, ExtractorRegistry
from .models import (
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
    KnowledgeDocument,
)
from .validation import validate_document_file

logger = logging.getLogger(__name__)


def get_chunking_config() -> ChunkingConfig:
    return ChunkingConfig(
        target_tokens=settings.INGESTION_TARGET_CHUNK_TOKENS,
        overlap_tokens=settings.INGESTION_CHUNK_OVERLAP_TOKENS,
        minimum_tokens=settings.INGESTION_MIN_CHUNK_TOKENS,
        maximum_tokens=settings.INGESTION_MAX_CHUNK_TOKENS,
    )


def process_document(
    document_id: str,
    *,
    reprocess: bool = False,
) -> IngestionJob:
    document = KnowledgeDocument.objects.get(pk=document_id)
    if not document.may_process:
        raise UnapprovedDocumentError(
            "Only approved, active documents may be processed."
        )
    version = document.versions.order_by("-created_at").first()
    if version is None:
        raise ExtractionError("No source version is registered.")

    config = get_chunking_config()
    config.validate()
    job = IngestionJob.objects.create(
        document=document,
        document_version=version,
        job_type=(
            IngestionJob.JobType.REPROCESS
            if reprocess
            else IngestionJob.JobType.PROCESS
        ),
        status=IngestionJob.Status.RUNNING,
        configuration=asdict(config),
        started_at=timezone.now(),
    )
    KnowledgeDocument.objects.filter(pk=document.pk).update(
        lifecycle_status=KnowledgeDocument.LifecycleStatus.PROCESSING,
        processing_status=KnowledgeDocument.ProcessingStatus.PROCESSING,
    )

    try:
        validated = validate_document_file(Path(version.source_file.path))
        extraction = (
            ExtractorRegistry().for_path(validated.path).extract(validated.path)
        )
        drafts = DocumentChunker(config).chunk(
            extraction,
            version_id=version.version_id,
        )
        if not drafts:
            raise ManualReviewRequired("No chunks could be generated safely.")
        _persist_result(document, version, job, extraction.text, extraction, drafts)
    except ManualReviewRequired as exc:
        _mark_manual_review(document, version, job, exc)
    except Exception as exc:
        _mark_failed(document, version, job, exc)
        if isinstance(exc, ExtractionError):
            raise
        raise ExtractionError("Document processing failed.") from exc
    return IngestionJob.objects.get(pk=job.pk)


@transaction.atomic
def _persist_result(
    document: KnowledgeDocument,
    version: DocumentVersion,
    job: IngestionJob,
    extracted_text: str,
    extraction: ExtractionResult,
    drafts: list[ChunkDraft],
) -> None:
    extraction_warnings = [warning.as_dict() for warning in extraction.warnings]
    version.chunks.update(
        retrieval_enabled=False,
        is_current_generation=False,
    )
    current_ids = {draft.chunk_id for draft in drafts}
    version.chunks.filter(
        origin=DocumentChunk.Origin.GENERATED,
    ).exclude(chunk_id__in=current_ids).filter(split_corrections__isnull=True).delete()
    created_by_sequence: dict[int, DocumentChunk] = {}
    for draft in drafts:
        duplicate = (
            created_by_sequence.get(draft.duplicate_sequence)
            if draft.duplicate_sequence
            else None
        )
        chunk, _ = DocumentChunk.objects.update_or_create(
            chunk_id=draft.chunk_id,
            defaults={
                "document": document,
                "document_version": version,
                "sequence": draft.sequence,
                "content": draft.text,
                "content_hash": draft.content_hash,
                "chapter": draft.chapter,
                "section": draft.section,
                "page_start": draft.page_start,
                "page_end": draft.page_end,
                "manufacturer": document.manufacturer,
                "equipment_family": document.equipment_family,
                "equipment_model": document.equipment_model,
                "subsystem": document.subsystem,
                "safety_priority": document.safety_priority,
                "access_level": document.access_level,
                "token_count": draft.token_count,
                "contains_warning": draft.contains_warning,
                "contains_caution": draft.contains_caution,
                "review_status": DocumentChunk.ReviewStatus.PENDING,
                "processing_warnings": [
                    warning.as_dict() for warning in draft.warnings
                ],
                "duplicate_of": duplicate,
                "origin": DocumentChunk.Origin.GENERATED,
                "parent_chunk": None,
                "retrieval_enabled": False,
                "is_current_generation": True,
                "reviewer_notes": "",
                "reviewed_by": None,
                "reviewed_at": None,
            },
        )
        created_by_sequence[draft.sequence] = chunk

    reapply_corrections(version.version_id)

    now = timezone.now()
    version.extracted_text = extracted_text
    version.page_count = extraction.page_count
    version.extraction_warnings = extraction_warnings
    version.extraction_errors = extraction.errors
    version.processed_at = now
    version.save(
        update_fields=[
            "extracted_text",
            "page_count",
            "extraction_warnings",
            "extraction_errors",
            "processed_at",
        ]
    )
    document.lifecycle_status = KnowledgeDocument.LifecycleStatus.PROCESSED
    document.processing_status = KnowledgeDocument.ProcessingStatus.PROCESSED
    document.processing_date = now
    document.checksum = version.checksum
    document.save(
        update_fields=[
            "lifecycle_status",
            "processing_status",
            "processing_date",
            "checksum",
            "updated_at",
        ]
    )
    job.status = IngestionJob.Status.COMPLETED
    job.warnings = extraction_warnings
    job.errors = list(extraction.errors)
    job.chunk_count = len(drafts)
    job.completed_at = now
    job.save(
        update_fields=[
            "status",
            "warnings",
            "errors",
            "chunk_count",
            "completed_at",
        ]
    )


def _mark_manual_review(
    document: KnowledgeDocument,
    version: DocumentVersion,
    job: IngestionJob,
    error: ManualReviewRequired,
) -> None:
    now = timezone.now()
    message = str(error)
    version.extraction_errors = [message]
    version.processed_at = now
    version.save(update_fields=["extraction_errors", "processed_at"])
    KnowledgeDocument.objects.filter(pk=document.pk).update(
        lifecycle_status=KnowledgeDocument.LifecycleStatus.FAILED,
        processing_status=KnowledgeDocument.ProcessingStatus.MANUAL_REVIEW,
        processing_date=now,
    )
    IngestionJob.objects.filter(pk=job.pk).update(
        status=IngestionJob.Status.MANUAL_REVIEW,
        errors=[message],
        completed_at=now,
    )


def _mark_failed(
    document: KnowledgeDocument,
    version: DocumentVersion,
    job: IngestionJob,
    error: Exception,
) -> None:
    now = timezone.now()
    message = str(error) or error.__class__.__name__
    logger.exception(
        "Knowledge document ingestion failed",
        extra={"document_id": document.pk, "job_id": str(job.pk)},
    )
    version.extraction_errors = [message]
    version.processed_at = now
    version.save(update_fields=["extraction_errors", "processed_at"])
    KnowledgeDocument.objects.filter(pk=document.pk).update(
        lifecycle_status=KnowledgeDocument.LifecycleStatus.FAILED,
        processing_status=KnowledgeDocument.ProcessingStatus.FAILED,
        processing_date=now,
    )
    IngestionJob.objects.filter(pk=job.pk).update(
        status=IngestionJob.Status.FAILED,
        errors=[message],
        completed_at=now,
    )
