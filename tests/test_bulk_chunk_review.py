import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.management import call_command
from openpyxl import load_workbook

from apps.knowledge_base.bulk_review import (
    REVIEW_COLUMNS,
    ReviewRow,
    apply_review_plans,
    chunk_export_row,
    export_review_workbook,
    load_review_rows,
    resolve_reviewer,
    validate_review_rows,
)
from apps.knowledge_base.corrections import content_hash
from apps.knowledge_base.models import (
    ChunkMetadataCorrection,
    ChunkSplitCorrection,
    DocumentChunk,
    DocumentVersion,
    KnowledgeDocument,
)


@pytest.fixture
def bulk_reviewer():
    return get_user_model().objects.create_superuser(
        username="bulk-reviewer",
        email="bulk@example.test",
        password="local-test-password",
    )


@pytest.fixture
def bulk_chunks(db) -> list[DocumentChunk]:
    document = KnowledgeDocument.objects.create(
        document_id="BULK-TEST-001",
        title="Synthetic bulk review source",
        manufacturer="Example",
        equipment_family="Robot",
        equipment_model="R-1",
        subsystem="safety",
        access_level=KnowledgeDocument.AccessLevel.INTERNAL,
        safety_priority=KnowledgeDocument.SafetyPriority.CRITICAL,
    )
    version = DocumentVersion.objects.create(
        version_id="BULK-TEST-001-v1",
        document=document,
        source_file="bulk/source.txt",
        source_filename="source.txt",
        checksum="b" * 64,
        file_size=100,
        media_type="text/plain",
    )
    contents = [
        (
            "1 SAFETY\n\n1.1 ENTRY\n\nWARNING: Stop before entry.\n\n"
            "1. Verify motion has stopped.\n2. Follow the approved procedure."
        ),
        "2 OPERATION\n\n2.1 START\n\nConfirm safeguards are functional.",
        "3 MAINTENANCE\n\n3.1 CHECK\n\nInspect the cable.",
    ]
    chunks = []
    for index, text in enumerate(contents, 1):
        chunks.append(
            DocumentChunk.objects.create(
                chunk_id=f"CHK-BULK-{index}",
                document=document,
                document_version=version,
                sequence=Decimal(index),
                content=text,
                content_hash=content_hash(text),
                chapter=f"{index} CHAPTER",
                section=f"{index}.1 SECTION",
                page_start=index,
                page_end=index,
                manufacturer=document.manufacturer,
                equipment_family=document.equipment_family,
                equipment_model=document.equipment_model,
                subsystem=document.subsystem,
                safety_priority=document.safety_priority,
                access_level=document.access_level,
                token_count=20,
                contains_warning=index == 1,
            )
        )
    return chunks


def review_row(
    chunk: DocumentChunk,
    action: str,
    **overrides,
) -> ReviewRow:
    exported = chunk_export_row(chunk)
    values = {
        "row_number": 2,
        "chunk_id": exported["chunk_id"],
        "source_content_hash": exported["source_content_hash"],
        "document_id": exported["document_id"],
        "document_version": exported["document_version"],
        "sequence": exported["sequence"],
        "chapter": exported["chapter"],
        "section": exported["section"],
        "page_start": exported["page_start"],
        "page_end": exported["page_end"],
        "token_count": exported["token_count"],
        "content": exported["content"],
        "contains_warning": exported["contains_warning"],
        "contains_caution": exported["contains_caution"],
        "processing_warnings": exported["processing_warnings"],
        "origin": exported["origin"],
        "review_status": exported["review_status"],
        "retrieval_enabled": exported["retrieval_enabled"],
        "reviewer_notes": "Reviewed against the synthetic source.",
        "proposed_action": action,
        "correction_payload": {},
        "validation_result": "",
    }
    values.update(overrides)
    return ReviewRow(**values)


def split_payload(chunk: DocumentChunk, count: int) -> dict:
    if count == 2:
        parts = chunk.content.split("\n\n1. Verify")
        contents = [parts[0], f"1. Verify{parts[1]}"]
    else:
        parts = chunk.content.split("\n\n")
        contents = [parts[0], parts[1], "\n\n".join(parts[2:])]
    return {
        "safety_confirmed": True,
        "artifact_note": "",
        "children": [
            {
                "content": text,
                "chapter": chunk.chapter,
                "section": chunk.section,
                "page_start": chunk.page_start,
                "page_end": chunk.page_end,
                "contains_warning": "WARNING" in text,
                "contains_caution": False,
                "retrieval_enabled": True,
                "reviewer_notes": "Synthetic child checked.",
            }
            for text in contents
        ],
    }


@pytest.mark.django_db
@pytest.mark.parametrize("suffix", [".xlsx", ".csv", ".json"])
def test_export_and_load_supported_formats(
    tmp_path: Path,
    bulk_chunks: list[DocumentChunk],
    suffix: str,
) -> None:
    path = tmp_path / f"review{suffix}"

    count = export_review_workbook("BULK-TEST-001", path)
    rows = load_review_rows(path)

    assert count == 3
    assert len(rows) == 3
    assert rows[0].chunk_id == bulk_chunks[0].chunk_id
    if suffix == ".xlsx":
        workbook = load_workbook(path, read_only=True)
        assert tuple(cell.value for cell in workbook.active[1]) == REVIEW_COLUMNS
        workbook.close()


@pytest.mark.django_db
def test_approve_and_exclude_record_reviewer(
    bulk_chunks: list[DocumentChunk],
    bulk_reviewer,
) -> None:
    approve = review_row(
        bulk_chunks[1],
        "APPROVE",
        retrieval_enabled=True,
    )
    exclude = review_row(
        bulk_chunks[2],
        "EXCLUDE",
        retrieval_enabled=False,
    )
    plans = validate_review_rows([approve, exclude])

    apply_review_plans(plans, bulk_reviewer)

    bulk_chunks[1].refresh_from_db()
    bulk_chunks[2].refresh_from_db()
    assert bulk_chunks[1].review_status == DocumentChunk.ReviewStatus.APPROVED
    assert bulk_chunks[1].retrieval_enabled is True
    assert bulk_chunks[1].reviewed_by == bulk_reviewer
    assert bulk_chunks[1].reviewed_at is not None
    assert bulk_chunks[2].review_status == DocumentChunk.ReviewStatus.EXCLUDED
    assert bulk_chunks[2].retrieval_enabled is False


@pytest.mark.django_db
def test_metadata_correction_is_audited(
    bulk_chunks: list[DocumentChunk],
    bulk_reviewer,
) -> None:
    row = review_row(
        bulk_chunks[1],
        "CORRECT_METADATA",
        chapter="2 SAFE OPERATION",
        section="2.1 CONTROLLED START",
        contains_caution=True,
    )
    plans = validate_review_rows([row])

    apply_review_plans(plans, bulk_reviewer)

    bulk_chunks[1].refresh_from_db()
    audit = ChunkMetadataCorrection.objects.get(source_chunk=bulk_chunks[1])
    assert bulk_chunks[1].content == row.content
    assert bulk_chunks[1].chapter == "2 SAFE OPERATION"
    assert audit.before_payload["chapter"] == "2 CHAPTER"
    assert audit.after_payload["contains_caution"] is True
    assert audit.created_by == bulk_reviewer


@pytest.mark.django_db
@pytest.mark.parametrize("count", [2, 3])
def test_bulk_split_uses_controlled_service(
    bulk_chunks: list[DocumentChunk],
    bulk_reviewer,
    count: int,
) -> None:
    source = bulk_chunks[0]
    row = review_row(
        source,
        "SPLIT",
        correction_payload=split_payload(source, count),
    )
    plans = validate_review_rows([row])
    assert not plans[0].errors

    apply_review_plans(plans, bulk_reviewer)

    source.refresh_from_db()
    assert source.review_status == DocumentChunk.ReviewStatus.SUPERSEDED
    assert source.retrieval_enabled is False
    assert (
        source.correction_children.filter(is_current_generation=True).count() == count
    )
    assert ChunkSplitCorrection.objects.filter(
        source_chunk=source,
        created_by=bulk_reviewer,
    ).exists()


@pytest.mark.django_db
def test_dry_run_command_makes_no_changes(
    tmp_path: Path,
    bulk_chunks: list[DocumentChunk],
    bulk_reviewer,
) -> None:
    path = tmp_path / "review.json"
    export_review_workbook("BULK-TEST-001", path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["rows"][1]["proposed_action"] = "APPROVE"
    payload["rows"][1]["reviewer_notes"] = "Dry-run only."
    payload["rows"][1]["retrieval_enabled"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")

    call_command(
        "import_chunk_reviews",
        str(path),
        "--dry-run",
        "--reviewer",
        bulk_reviewer.username,
    )

    bulk_chunks[1].refresh_from_db()
    assert bulk_chunks[1].review_status == DocumentChunk.ReviewStatus.PENDING
    assert path.with_suffix(".dry-run.json").exists()

    call_command(
        "import_chunk_reviews",
        str(path),
        "--apply",
        "--reviewer",
        bulk_reviewer.username,
    )

    bulk_chunks[1].refresh_from_db()
    assert bulk_chunks[1].review_status == DocumentChunk.ReviewStatus.APPROVED
    assert path.with_suffix(".apply-report.json").exists()


@pytest.mark.django_db
def test_transaction_rolls_back_on_runtime_failure(
    monkeypatch,
    bulk_chunks: list[DocumentChunk],
    bulk_reviewer,
) -> None:
    approve = review_row(
        bulk_chunks[1],
        "APPROVE",
        retrieval_enabled=True,
    )
    split = review_row(
        bulk_chunks[0],
        "SPLIT",
        row_number=3,
        correction_payload=split_payload(bulk_chunks[0], 2),
    )
    plans = validate_review_rows([approve, split])

    def fail_split(*args, **kwargs):
        raise ValidationError("Synthetic apply failure.")

    monkeypatch.setattr(
        "apps.knowledge_base.bulk_review.apply_split",
        fail_split,
    )
    with pytest.raises(ValidationError, match="Synthetic apply failure"):
        apply_review_plans(plans, bulk_reviewer)

    bulk_chunks[1].refresh_from_db()
    assert bulk_chunks[1].review_status == DocumentChunk.ReviewStatus.PENDING
    assert bulk_chunks[1].retrieval_enabled is False


@pytest.mark.django_db
def test_stale_hash_safety_and_duplicate_content_are_rejected(
    bulk_chunks: list[DocumentChunk],
) -> None:
    stale = review_row(
        bulk_chunks[1],
        "APPROVE",
        source_content_hash="0" * 64,
    )
    unsafe = review_row(
        bulk_chunks[0],
        "APPROVE",
        correction_payload={},
    )
    duplicate_text = bulk_chunks[1].content
    bulk_chunks[2].content = duplicate_text
    bulk_chunks[2].content_hash = bulk_chunks[1].content_hash
    bulk_chunks[2].save(update_fields=["content", "content_hash"])
    first = review_row(bulk_chunks[1], "APPROVE", retrieval_enabled=True)
    second = review_row(
        bulk_chunks[2],
        "APPROVE",
        row_number=3,
        retrieval_enabled=True,
    )

    stale_plan = validate_review_rows([stale])[0]
    unsafe_plan = validate_review_rows([unsafe])[0]
    duplicate_plans = validate_review_rows([first, second])

    assert "Source content hash mismatch." in stale_plan.errors
    assert any("Safety confirmation" in error for error in unsafe_plan.errors)
    assert any("duplicates chunk" in error for error in duplicate_plans[1].errors)


@pytest.mark.django_db
def test_reviewer_permissions_are_required(bulk_reviewer) -> None:
    ordinary = get_user_model().objects.create_user(username="ordinary")

    assert resolve_reviewer(bulk_reviewer.username) == bulk_reviewer
    with pytest.raises(ValidationError, match="lacks staff"):
        resolve_reviewer(ordinary.username)
