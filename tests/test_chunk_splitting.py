from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.knowledge_base.corrections import (
    SPLIT_MARKER,
    SplitSegment,
    apply_split,
    content_hash,
    reapply_corrections,
)
from apps.knowledge_base.models import (
    ChunkSplitCorrection,
    DocumentChunk,
    DocumentVersion,
    KnowledgeDocument,
)


@pytest.fixture
def staff_user():
    return get_user_model().objects.create_superuser(
        username="chunk-reviewer",
        email="reviewer@example.test",
        password="local-test-password",
    )


@pytest.fixture
def source_chunk(db) -> DocumentChunk:
    document = KnowledgeDocument.objects.create(
        document_id="SPLIT-TEST-001",
        title="Synthetic mixed front matter",
        document_code="SPLIT-001",
        document_type=KnowledgeDocument.DocumentType.SAFETY_HANDBOOK,
        manufacturer="Example Manufacturer",
        equipment_family="Test Robot",
        equipment_model="TR-1",
        subsystem="safety",
        access_level=KnowledgeDocument.AccessLevel.RESTRICTED,
        safety_priority=KnowledgeDocument.SafetyPriority.CRITICAL,
    )
    version = DocumentVersion.objects.create(
        version_id="SPLIT-TEST-001-v1",
        document=document,
        source_file="SPLIT-TEST-001/v1/fixture.txt",
        source_filename="fixture.txt",
        checksum="a" * 64,
        file_size=100,
        media_type="text/plain",
    )
    content = (
        "SAFETY HANDBOOK\n\n"
        "Original instructions and revision information.\n\n"
        "GENERAL PRECAUTIONS\n\n"
        "WARNING: Keep this warning with the following procedure.\n"
        "1. Stop work before entering the safeguarded area.\n"
        "2. Follow the approved site procedure."
    )
    source = DocumentChunk.objects.create(
        chunk_id="CHK-SOURCE",
        document=document,
        document_version=version,
        sequence=Decimal("1"),
        content=content,
        content_hash=content_hash(content),
        chapter="",
        section="",
        page_start=1,
        page_end=2,
        manufacturer=document.manufacturer,
        equipment_family=document.equipment_family,
        equipment_model=document.equipment_model,
        subsystem=document.subsystem,
        safety_priority=document.safety_priority,
        access_level=document.access_level,
        token_count=35,
        contains_warning=True,
        review_status=DocumentChunk.ReviewStatus.REQUIRES_CORRECTION,
    )
    DocumentChunk.objects.create(
        chunk_id="CHK-NEXT",
        document=document,
        document_version=version,
        sequence=Decimal("2"),
        content="Next section.",
        content_hash=content_hash("Next section."),
        manufacturer=document.manufacturer,
        equipment_family=document.equipment_family,
        equipment_model=document.equipment_model,
        subsystem=document.subsystem,
        safety_priority=document.safety_priority,
        access_level=document.access_level,
        token_count=2,
    )
    return source


def make_segment(
    source: DocumentChunk,
    content: str,
    *,
    retrieval_enabled: bool = True,
    page_start: int | None = 1,
    page_end: int | None = 2,
) -> SplitSegment:
    return SplitSegment(
        content=content,
        chapter=source.chapter,
        section=source.section,
        page_start=page_start,
        page_end=page_end,
        contains_warning="warning" in content.casefold(),
        contains_caution="caution" in content.casefold(),
        retrieval_enabled=retrieval_enabled,
        reviewer_notes="Compared with the synthetic fixture.",
    )


def split_source(source: DocumentChunk) -> list[str]:
    return source.content.split("\n\nGENERAL PRECAUTIONS\n\n")


@pytest.mark.django_db
def test_two_child_split_inherits_metadata_and_supersedes_source(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    first, second = split_source(source_chunk)
    segments = [
        make_segment(source_chunk, first),
        make_segment(source_chunk, f"GENERAL PRECAUTIONS\n\n{second}"),
    ]

    correction = apply_split(
        source_chunk,
        segments,
        reviewer=staff_user,
        artifact_note="",
        safety_confirmed=True,
        safety_confirmation_required=True,
    )

    children = list(
        DocumentChunk.objects.filter(parent_chunk=source_chunk).order_by("sequence")
    )
    source_chunk.refresh_from_db()
    assert correction.status == ChunkSplitCorrection.Status.APPLIED
    assert len(children) == 2
    assert source_chunk.review_status == DocumentChunk.ReviewStatus.SUPERSEDED
    assert source_chunk.retrieval_enabled is False
    assert [child.sequence for child in children] == sorted(
        child.sequence for child in children
    )
    assert source_chunk.sequence < children[0].sequence < children[1].sequence
    assert children[1].sequence < Decimal("2")
    assert all(child.document_id == source_chunk.document_id for child in children)
    assert all(
        child.document_version_id == source_chunk.document_version_id
        for child in children
    )
    assert all(child.manufacturer == source_chunk.manufacturer for child in children)
    assert all(
        child.equipment_model == source_chunk.equipment_model for child in children
    )
    assert all(child.access_level == source_chunk.access_level for child in children)
    assert all(child.reviewed_by == staff_user for child in children)
    assert all(child.origin == DocumentChunk.Origin.CORRECTION for child in children)


@pytest.mark.django_db
def test_split_supports_more_than_two_children(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    parts = source_chunk.content.split("\n\n")
    segments = [
        make_segment(source_chunk, parts[0]),
        make_segment(source_chunk, parts[1]),
        make_segment(source_chunk, "\n\n".join(parts[2:])),
    ]
    correction = apply_split(
        source_chunk,
        segments,
        reviewer=staff_user,
        artifact_note="",
        safety_confirmed=True,
        safety_confirmation_required=True,
    )

    children = list(
        DocumentChunk.objects.filter(parent_chunk=source_chunk).order_by("sequence")
    )
    assert len(children) == 3
    assert len({child.chunk_id for child in children}) == 3
    assert all(len(child.content_hash) == 64 for child in children)
    assert correction.segment_payload[2]["content"] == segments[2].content


@pytest.mark.django_db
def test_duplicate_active_child_content_is_rejected(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    repeated = make_segment(source_chunk, source_chunk.content)
    with pytest.raises(ValidationError, match="Duplicate child content"):
        apply_split(
            source_chunk,
            [repeated, repeated],
            reviewer=staff_user,
            artifact_note="Duplicated during correction for test.",
            safety_confirmed=True,
            safety_confirmation_required=True,
        )


@pytest.mark.django_db
def test_empty_child_and_invalid_pages_are_rejected(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    valid = make_segment(source_chunk, source_chunk.content)
    empty = make_segment(source_chunk, " ")
    with pytest.raises(ValidationError, match="cannot be empty"):
        apply_split(
            source_chunk,
            [valid, empty],
            reviewer=staff_user,
            artifact_note="test",
            safety_confirmed=True,
            safety_confirmation_required=True,
        )

    outside = make_segment(source_chunk, "Second", page_start=1, page_end=3)
    with pytest.raises(ValidationError, match="inside the source"):
        apply_split(
            source_chunk,
            [valid, outside],
            reviewer=staff_user,
            artifact_note="test",
            safety_confirmed=True,
            safety_confirmation_required=True,
        )


@pytest.mark.django_db
def test_content_loss_requires_artifact_note(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    with pytest.raises(ValidationError, match="Describe every removed"):
        apply_split(
            source_chunk,
            [
                make_segment(source_chunk, "SAFETY HANDBOOK"),
                make_segment(source_chunk, "GENERAL PRECAUTIONS"),
            ],
            reviewer=staff_user,
            artifact_note="",
            safety_confirmed=True,
            safety_confirmation_required=True,
        )


@pytest.mark.django_db
def test_warning_boundary_requires_confirmation(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    first, second = split_source(source_chunk)
    with pytest.raises(ValidationError, match="Confirm that safety"):
        apply_split(
            source_chunk,
            [
                make_segment(source_chunk, first),
                make_segment(source_chunk, f"GENERAL PRECAUTIONS\n\n{second}"),
            ],
            reviewer=staff_user,
            artifact_note="",
            safety_confirmed=False,
            safety_confirmation_required=True,
        )


@pytest.mark.django_db
def test_correction_reapplies_with_stable_child_ids(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    first, second = split_source(source_chunk)
    correction = apply_split(
        source_chunk,
        [
            make_segment(source_chunk, first),
            make_segment(source_chunk, f"GENERAL PRECAUTIONS\n\n{second}"),
        ],
        reviewer=staff_user,
        artifact_note="",
        safety_confirmed=True,
        safety_confirmation_required=True,
    )
    before = set(
        DocumentChunk.objects.filter(parent_chunk=source_chunk).values_list(
            "chunk_id", flat=True
        )
    )
    DocumentChunk.objects.filter(parent_chunk=source_chunk).update(
        retrieval_enabled=False,
        is_current_generation=False,
    )

    reapply_corrections(source_chunk.document_version_id)

    correction.refresh_from_db()
    after = set(
        DocumentChunk.objects.filter(
            parent_chunk=correction.source_chunk,
            is_current_generation=True,
        ).values_list("chunk_id", flat=True)
    )
    assert correction.status == ChunkSplitCorrection.Status.APPLIED
    assert before == after


@pytest.mark.django_db
def test_source_change_marks_correction_stale(
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    first, second = split_source(source_chunk)
    correction = apply_split(
        source_chunk,
        [
            make_segment(source_chunk, first),
            make_segment(source_chunk, f"GENERAL PRECAUTIONS\n\n{second}"),
        ],
        reviewer=staff_user,
        artifact_note="",
        safety_confirmed=True,
        safety_confirmation_required=True,
    )
    source_chunk.content = f"{source_chunk.content}\nChanged extraction."
    source_chunk.content_hash = content_hash(source_chunk.content)
    source_chunk.save(update_fields=["content", "content_hash"])

    reapply_corrections(source_chunk.document_version_id)

    correction.refresh_from_db()
    assert correction.status == ChunkSplitCorrection.Status.STALE
    assert not DocumentChunk.objects.filter(
        parent_chunk=source_chunk,
        retrieval_enabled=True,
    ).exists()


@pytest.mark.django_db
def test_admin_cancel_and_permissions_do_not_modify_source(
    client,
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    url = reverse(
        "admin:knowledge_base_documentchunk_split",
        args=[source_chunk.pk],
    )
    anonymous_response = client.get(url)
    assert anonymous_response.status_code == 302

    ordinary = get_user_model().objects.create_user(
        username="ordinary-reviewer",
        password="local-test-password",
    )
    client.force_login(ordinary)
    assert client.get(url).status_code == 302

    client.force_login(staff_user)
    response = client.get(url)
    assert response.status_code == 200
    assert b"Immutable source chunk" in response.content
    source_chunk.refresh_from_db()
    assert source_chunk.review_status == DocumentChunk.ReviewStatus.REQUIRES_CORRECTION
    assert not ChunkSplitCorrection.objects.exists()


@pytest.mark.django_db
def test_mixed_front_matter_admin_preview_creates_three_proposals(
    client,
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    client.force_login(staff_user)
    url = reverse(
        "admin:knowledge_base_documentchunk_split",
        args=[source_chunk.pk],
    )
    marked = source_chunk.content.replace(
        "\n\nOriginal instructions",
        f"\n\n{SPLIT_MARKER}\n\nOriginal instructions",
    ).replace(
        "\n\nGENERAL PRECAUTIONS",
        f"\n\n{SPLIT_MARKER}\n\nGENERAL PRECAUTIONS",
    )

    response = client.post(
        url,
        {"stage": "preview", "marked_content": marked},
    )

    assert response.status_code == 200
    assert response.content.count(b"Proposed child") == 3
    assert not ChunkSplitCorrection.objects.exists()


@pytest.mark.django_db
def test_staff_can_apply_previewed_split(
    client,
    source_chunk: DocumentChunk,
    staff_user,
) -> None:
    client.force_login(staff_user)
    url = reverse(
        "admin:knowledge_base_documentchunk_split",
        args=[source_chunk.pk],
    )
    first, second = split_source(source_chunk)
    marked = f"{first}\n\n{SPLIT_MARKER}\n\nGENERAL PRECAUTIONS\n\n{second}"
    response = client.post(
        url,
        {
            "stage": "apply",
            "source_content_hash": source_chunk.content_hash,
            "marked_content": marked,
            "artifact_note": "",
            "safety_confirmed": "on",
            "segments-TOTAL_FORMS": "2",
            "segments-INITIAL_FORMS": "0",
            "segments-MIN_NUM_FORMS": "2",
            "segments-MAX_NUM_FORMS": "1000",
            "segments-0-content": first,
            "segments-0-chapter": "",
            "segments-0-section": "Front matter",
            "segments-0-page_start": "1",
            "segments-0-page_end": "1",
            "segments-0-retrieval_enabled": "on",
            "segments-0-reviewer_notes": "Front matter checked.",
            "segments-1-content": f"GENERAL PRECAUTIONS\n\n{second}",
            "segments-1-chapter": "GENERAL PRECAUTIONS",
            "segments-1-section": "",
            "segments-1-page_start": "2",
            "segments-1-page_end": "2",
            "segments-1-contains_warning": "on",
            "segments-1-retrieval_enabled": "on",
            "segments-1-reviewer_notes": "Safety procedure checked.",
        },
    )

    assert response.status_code == 302
    assert ChunkSplitCorrection.objects.filter(
        source_chunk=source_chunk,
        status=ChunkSplitCorrection.Status.APPLIED,
    ).exists()
    assert (
        DocumentChunk.objects.filter(
            parent_chunk=source_chunk,
            is_current_generation=True,
        ).count()
        == 2
    )
