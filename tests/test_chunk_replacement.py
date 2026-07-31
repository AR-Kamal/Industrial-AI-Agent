from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.knowledge_base.corrections import content_hash
from apps.knowledge_base.models import (
    ChunkReplacementCorrection,
    DocumentChunk,
    DocumentVersion,
    KnowledgeDocument,
)
from apps.knowledge_base.replacements import (
    reapply_replacements,
    replace_correction_child,
)


@pytest.fixture
def replacement_reviewer():
    return get_user_model().objects.create_superuser(
        username="replacement-reviewer",
        email="replacement@example.test",
        password="local-test-password",
    )


@pytest.fixture
def replacement_chunks(db) -> tuple[DocumentChunk, DocumentChunk]:
    document = KnowledgeDocument.objects.create(
        document_id="REPLACE-TEST-001",
        title="Synthetic replacement source",
        manufacturer="Example",
        equipment_family="Robot",
        equipment_model="R-1",
        subsystem="safety",
        safety_priority=KnowledgeDocument.SafetyPriority.CRITICAL,
    )
    version = DocumentVersion.objects.create(
        version_id="REPLACE-TEST-001-v1",
        document=document,
        source_file="replace/source.txt",
        source_filename="source.txt",
        checksum="d" * 64,
        file_size=100,
        media_type="text/plain",
    )
    parent_text = "1 SAFETY\n\nWARNING: Follow the complete approved procedure."
    parent = DocumentChunk.objects.create(
        chunk_id="CHK-REPLACE-PARENT",
        document=document,
        document_version=version,
        sequence=Decimal("1"),
        content=parent_text,
        content_hash=content_hash(parent_text),
        chapter="1 SAFETY",
        section="1.1 PROCEDURE",
        page_start=1,
        page_end=2,
        manufacturer=document.manufacturer,
        equipment_family=document.equipment_family,
        equipment_model=document.equipment_model,
        subsystem=document.subsystem,
        safety_priority=document.safety_priority,
        access_level=document.access_level,
        token_count=10,
        contains_warning=True,
        review_status=DocumentChunk.ReviewStatus.SUPERSEDED,
        retrieval_enabled=False,
    )
    child_text = "WARNING: Follow the approved"
    child = DocumentChunk.objects.create(
        chunk_id="CHK-C-REPLACE-SOURCE",
        document=document,
        document_version=version,
        sequence=Decimal("1.5000"),
        content=child_text,
        content_hash=content_hash(child_text),
        chapter="1 SAFETY",
        section="1.1 PROCEDURE",
        page_start=1,
        page_end=1,
        manufacturer=document.manufacturer,
        equipment_family=document.equipment_family,
        equipment_model=document.equipment_model,
        subsystem=document.subsystem,
        safety_priority=document.safety_priority,
        access_level=document.access_level,
        token_count=5,
        contains_warning=True,
        origin=DocumentChunk.Origin.CORRECTION,
        parent_chunk=parent,
        review_status=DocumentChunk.ReviewStatus.APPROVED,
        retrieval_enabled=True,
    )
    return parent, child


def apply_replacement(child: DocumentChunk, reviewer):
    return replace_correction_child(
        child.chunk_id,
        "WARNING: Follow the complete approved procedure.",
        expected_source_hash=child.content_hash,
        reviewer=reviewer,
        reviewer_notes="Compared with the synthetic source.",
        reason="Complete the truncated final sentence.",
        safety_confirmed=True,
    )


@pytest.mark.django_db
def test_replace_child_preserves_source_and_creates_audit(
    replacement_chunks,
    replacement_reviewer,
) -> None:
    parent, child = replacement_chunks
    original_content = child.content
    original_hash = child.content_hash

    audit = apply_replacement(child, replacement_reviewer)

    child.refresh_from_db()
    replacement = audit.replacement_child
    assert child.content == original_content
    assert child.content_hash == original_hash
    assert child.parent_chunk == parent
    assert child.review_status == DocumentChunk.ReviewStatus.SUPERSEDED
    assert child.retrieval_enabled is False
    assert child.is_current_generation is False
    assert replacement.origin == DocumentChunk.Origin.CORRECTION_REPLACEMENT
    assert replacement.chapter == child.chapter
    assert replacement.section == child.section
    assert replacement.page_start == child.page_start
    assert replacement.page_end == child.page_end
    assert replacement.parent_chunk == parent
    assert replacement.retrieval_enabled is True
    assert replacement.review_status == DocumentChunk.ReviewStatus.APPROVED
    assert replacement.reviewed_by == replacement_reviewer
    assert replacement.chunk_id.startswith("CHK-R-")
    assert audit.old_content_hash == original_hash
    assert audit.new_content_hash == replacement.content_hash
    assert audit.document == child.document
    assert audit.document_version == child.document_version


@pytest.mark.django_db
def test_replacement_id_is_stable_after_reapplication(
    replacement_chunks,
    replacement_reviewer,
) -> None:
    _, child = replacement_chunks
    audit = apply_replacement(child, replacement_reviewer)
    replacement_id = audit.replacement_child_id
    DocumentChunk.objects.filter(pk=replacement_id).update(
        retrieval_enabled=False,
        is_current_generation=False,
    )
    child.review_status = DocumentChunk.ReviewStatus.APPROVED
    child.retrieval_enabled = True
    child.is_current_generation = True
    child.save()

    reapply_replacements(child.document_version_id)

    audit.refresh_from_db()
    assert audit.status == ChunkReplacementCorrection.Status.APPLIED
    assert audit.replacement_child_id == replacement_id
    assert DocumentChunk.objects.get(pk=replacement_id).retrieval_enabled is True


@pytest.mark.django_db
def test_changed_source_marks_replacement_stale(
    replacement_chunks,
    replacement_reviewer,
) -> None:
    _, child = replacement_chunks
    audit = apply_replacement(child, replacement_reviewer)
    DocumentChunk.objects.filter(pk=audit.replacement_child_id).update(
        retrieval_enabled=False,
        is_current_generation=False,
    )
    child.content_hash = "0" * 64
    child.review_status = DocumentChunk.ReviewStatus.APPROVED
    child.is_current_generation = True
    child.save()

    reapply_replacements(child.document_version_id)

    audit.refresh_from_db()
    assert audit.status == ChunkReplacementCorrection.Status.STALE
    assert audit.replacement_child.retrieval_enabled is False


@pytest.mark.django_db
def test_generated_superseded_hash_empty_and_unchanged_are_rejected(
    replacement_chunks,
    replacement_reviewer,
) -> None:
    parent, child = replacement_chunks
    common = {
        "reviewer": replacement_reviewer,
        "reviewer_notes": "Reviewed.",
        "reason": "Correction.",
        "safety_confirmed": True,
    }
    with pytest.raises(ValidationError, match="Only a correction child"):
        replace_correction_child(
            parent.pk,
            "Changed",
            expected_source_hash=parent.content_hash,
            **common,
        )
    child.review_status = DocumentChunk.ReviewStatus.SUPERSEDED
    child.save(update_fields=["review_status"])
    with pytest.raises(ValidationError, match="already superseded"):
        replace_correction_child(
            child.pk,
            "Changed",
            expected_source_hash=child.content_hash,
            **common,
        )
    child.review_status = DocumentChunk.ReviewStatus.APPROVED
    child.save(update_fields=["review_status"])
    with pytest.raises(ValidationError, match="hash mismatch"):
        replace_correction_child(
            child.pk,
            "Changed",
            expected_source_hash="0" * 64,
            **common,
        )
    with pytest.raises(ValidationError, match="cannot be empty"):
        replace_correction_child(
            child.pk,
            " ",
            expected_source_hash=child.content_hash,
            **common,
        )
    with pytest.raises(ValidationError, match="must differ"):
        replace_correction_child(
            child.pk,
            child.content,
            expected_source_hash=child.content_hash,
            **common,
        )


@pytest.mark.django_db
def test_page_notes_and_safety_validation(
    replacement_chunks,
    replacement_reviewer,
) -> None:
    parent, child = replacement_chunks
    child.page_end = parent.page_end + 1
    child.save(update_fields=["page_end"])
    with pytest.raises(ValidationError, match="outside"):
        apply_replacement(child, replacement_reviewer)
    child.page_end = 1
    child.save(update_fields=["page_end"])
    with pytest.raises(ValidationError, match="notes"):
        replace_correction_child(
            child.pk,
            "WARNING: Complete.",
            expected_source_hash=child.content_hash,
            reviewer=replacement_reviewer,
            reviewer_notes="",
            reason="Correction.",
            safety_confirmed=True,
        )
    with pytest.raises(ValidationError, match="Safety confirmation"):
        replace_correction_child(
            child.pk,
            "WARNING: Complete.",
            expected_source_hash=child.content_hash,
            reviewer=replacement_reviewer,
            reviewer_notes="Reviewed.",
            reason="Correction.",
            safety_confirmed=False,
        )


@pytest.mark.django_db
def test_management_command_records_reviewer(
    tmp_path: Path,
    replacement_chunks,
    replacement_reviewer,
) -> None:
    _, child = replacement_chunks
    content_file = tmp_path / "replacement.txt"
    content_file.write_text(
        "WARNING: Follow the complete approved procedure.",
        encoding="utf-8",
    )

    call_command(
        "replace_correction_child",
        child.pk,
        "--content-file",
        str(content_file),
        "--source-hash",
        child.content_hash,
        "--reason",
        "Complete truncated sentence.",
        "--reviewer-notes",
        "Verified against synthetic source.",
        "--reviewer",
        replacement_reviewer.username,
        "--safety-confirmed",
    )

    audit = ChunkReplacementCorrection.objects.get(replaced_child=child)
    assert audit.reviewer == replacement_reviewer
    assert audit.created_at is not None
