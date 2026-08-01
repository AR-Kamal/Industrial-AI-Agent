import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class KnowledgeDocument(models.Model):
    class DocumentType(models.TextChoices):
        SAFETY_HANDBOOK = "safety_handbook", "Safety handbook"
        MANUAL = "manual", "Manual"
        PROCEDURE = "procedure", "Procedure"
        TROUBLESHOOTING_GUIDE = "troubleshooting_guide", "Troubleshooting guide"
        TRAINING = "training", "Training material"
        OTHER = "other", "Other"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    class LifecycleStatus(models.TextChoices):
        UPLOADED = "uploaded", "Uploaded"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        ARCHIVED = "archived", "Archived"
        REJECTED = "rejected", "Rejected"

    class VerificationStatus(models.TextChoices):
        UNVERIFIED = "unverified", "Unverified"
        REQUIRES_VERIFICATION = (
            "requires_version_verification",
            "Requires current-version verification",
        )
        VERIFIED_CURRENT = "verified_current", "Verified current"

    class AccessLevel(models.TextChoices):
        INTERNAL = "internal", "Internal"
        RESTRICTED = "restricted", "Restricted"

    class SafetyPriority(models.TextChoices):
        NORMAL = "normal", "Normal"
        HIGH = "high", "High"
        CRITICAL = "critical", "Critical"

    class ProcessingStatus(models.TextChoices):
        NOT_PROCESSED = "not_processed", "Not processed"
        PROCESSING = "processing", "Processing"
        PROCESSED = "processed", "Processed"
        FAILED = "failed", "Failed"
        MANUAL_REVIEW = "manual_review", "Manual review required"

    document_id = models.CharField(primary_key=True, max_length=100)
    title = models.CharField(max_length=300)
    document_code = models.CharField(max_length=100, blank=True)
    document_type = models.CharField(
        max_length=50,
        choices=DocumentType.choices,
        default=DocumentType.OTHER,
    )
    manufacturer = models.CharField(max_length=150)
    equipment_family = models.CharField(max_length=200, blank=True)
    equipment_model = models.CharField(max_length=200, blank=True)
    subsystem = models.CharField(max_length=150, blank=True)
    version_or_edition = models.CharField(max_length=100, blank=True)
    revision_or_effective_date = models.DateField(null=True, blank=True)
    revision_label = models.CharField(max_length=50, blank=True)
    language = models.CharField(max_length=50, default="English")
    approval_status = models.CharField(
        max_length=20,
        choices=ApprovalStatus.choices,
        default=ApprovalStatus.PENDING,
    )
    lifecycle_status = models.CharField(
        max_length=20,
        choices=LifecycleStatus.choices,
        default=LifecycleStatus.UPLOADED,
    )
    current_version_verification_status = models.CharField(
        max_length=40,
        choices=VerificationStatus.choices,
        default=VerificationStatus.UNVERIFIED,
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_knowledge_documents",
    )
    source_filename = models.CharField(max_length=255, blank=True)
    access_level = models.CharField(
        max_length=20,
        choices=AccessLevel.choices,
        default=AccessLevel.INTERNAL,
    )
    safety_priority = models.CharField(
        max_length=20,
        choices=SafetyPriority.choices,
        default=SafetyPriority.NORMAL,
    )
    checksum = models.CharField(max_length=64, blank=True, db_index=True)
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.NOT_PROCESSED,
    )
    processing_date = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["manufacturer", "document_code", "title"]

    def __str__(self) -> str:
        return f"{self.document_id} — {self.title}"

    @property
    def may_process(self) -> bool:
        return (
            self.approval_status == self.ApprovalStatus.APPROVED
            and self.lifecycle_status
            not in {self.LifecycleStatus.ARCHIVED, self.LifecycleStatus.REJECTED}
        )


def document_upload_path(instance: "DocumentVersion", filename: str) -> str:
    safe_name = filename.replace("\\", "/").split("/")[-1]
    return f"{instance.document_id}/{instance.version_id}/{safe_name}"


class DocumentVersion(models.Model):
    version_id = models.CharField(primary_key=True, max_length=140)
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="versions",
    )
    version_or_edition = models.CharField(max_length=100, blank=True)
    revision_or_effective_date = models.DateField(null=True, blank=True)
    revision_label = models.CharField(max_length=50, blank=True)
    source_file = models.FileField(upload_to=document_upload_path, max_length=500)
    source_filename = models.CharField(max_length=255)
    checksum = models.CharField(max_length=64, unique=True)
    file_size = models.PositiveBigIntegerField()
    media_type = models.CharField(max_length=100)
    extracted_text = models.TextField(blank=True)
    page_count = models.PositiveIntegerField(default=0)
    extraction_warnings = models.JSONField(default=list, blank=True)
    extraction_errors = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.version_id


class DocumentChunk(models.Model):
    class ReviewStatus(models.TextChoices):
        PENDING = "pending", "Pending review"
        APPROVED = "approved", "Approved"
        REQUIRES_CORRECTION = "requires_correction", "Requires correction"
        EXCLUDED = "excluded", "Excluded from retrieval"
        SUPERSEDED = "superseded", "Superseded by correction"

    class Origin(models.TextChoices):
        GENERATED = "generated", "Generated"
        CORRECTION = "correction", "Correction child"
        CORRECTION_REPLACEMENT = (
            "correction_replacement",
            "Correction replacement",
        )

    chunk_id = models.CharField(primary_key=True, max_length=80)
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name="chunks",
    )
    sequence = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        validators=[MinValueValidator(1)],
    )
    content = models.TextField()
    content_hash = models.CharField(max_length=64, db_index=True)
    chapter = models.CharField(max_length=300, blank=True)
    section = models.CharField(max_length=300, blank=True)
    page_start = models.PositiveIntegerField(null=True, blank=True)
    page_end = models.PositiveIntegerField(null=True, blank=True)
    manufacturer = models.CharField(max_length=150)
    equipment_family = models.CharField(max_length=200, blank=True)
    equipment_model = models.CharField(max_length=200, blank=True)
    subsystem = models.CharField(max_length=150, blank=True)
    safety_priority = models.CharField(max_length=20)
    access_level = models.CharField(
        max_length=20,
        default=KnowledgeDocument.AccessLevel.INTERNAL,
    )
    token_count = models.PositiveIntegerField(default=0)
    contains_warning = models.BooleanField(default=False)
    contains_caution = models.BooleanField(default=False)
    review_status = models.CharField(
        max_length=30,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
    )
    processing_warnings = models.JSONField(default=list, blank=True)
    origin = models.CharField(
        max_length=30,
        choices=Origin.choices,
        default=Origin.GENERATED,
    )
    parent_chunk = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="correction_children",
    )
    retrieval_enabled = models.BooleanField(default=False)
    is_current_generation = models.BooleanField(default=True)
    reviewer_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reviewed_document_chunks",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicates",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document_version", "sequence"]
        constraints = [
            models.UniqueConstraint(
                fields=["document_version", "sequence"],
                condition=models.Q(is_current_generation=True),
                name="unique_current_chunk_sequence_per_version",
            ),
            models.UniqueConstraint(
                fields=["document_version", "content_hash"],
                condition=models.Q(
                    retrieval_enabled=True,
                    is_current_generation=True,
                ),
                name="unique_active_chunk_content_per_version",
            ),
        ]

    def __str__(self) -> str:
        return self.chunk_id


class ChunkSplitCorrection(models.Model):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        STALE = "stale", "Stale — revalidation required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_chunk = models.ForeignKey(
        DocumentChunk,
        on_delete=models.PROTECT,
        related_name="split_corrections",
    )
    source_content_hash = models.CharField(max_length=64)
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.PROTECT,
        related_name="split_corrections",
    )
    segment_payload = models.JSONField(default=list)
    artifact_changes = models.JSONField(default=list, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.APPLIED,
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chunk_split_corrections",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Split {self.source_chunk_id} ({self.status})"


class ChunkMetadataCorrection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_chunk = models.ForeignKey(
        DocumentChunk,
        on_delete=models.PROTECT,
        related_name="metadata_corrections",
    )
    source_content_hash = models.CharField(max_length=64)
    before_payload = models.JSONField()
    after_payload = models.JSONField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chunk_metadata_corrections",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Metadata correction for {self.source_chunk_id}"


class ChunkReplacementCorrection(models.Model):
    class Status(models.TextChoices):
        APPLIED = "applied", "Applied"
        STALE = "stale", "Stale — revalidation required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    replaced_child = models.OneToOneField(
        DocumentChunk,
        on_delete=models.PROTECT,
        related_name="replacement_correction",
    )
    replacement_child = models.ForeignKey(
        DocumentChunk,
        on_delete=models.PROTECT,
        related_name="replacement_result_for",
    )
    old_content_hash = models.CharField(max_length=64)
    new_content_hash = models.CharField(max_length=64)
    corrected_content = models.TextField()
    reason = models.TextField()
    reviewer_notes = models.TextField()
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="chunk_replacement_corrections",
    )
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.PROTECT,
        related_name="chunk_replacement_corrections",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.PROTECT,
        related_name="chunk_replacement_corrections",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.APPLIED,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Replace {self.replaced_child_id} with {self.replacement_child_id}"


class IngestionJob(models.Model):
    class JobType(models.TextChoices):
        PROCESS = "process", "Process"
        REPROCESS = "reprocess", "Reprocess"

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"
        FAILED = "failed", "Failed"
        MANUAL_REVIEW = "manual_review", "Manual review required"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.ForeignKey(
        KnowledgeDocument,
        on_delete=models.CASCADE,
        related_name="ingestion_jobs",
    )
    document_version = models.ForeignKey(
        DocumentVersion,
        on_delete=models.CASCADE,
        related_name="ingestion_jobs",
    )
    job_type = models.CharField(
        max_length=20,
        choices=JobType.choices,
        default=JobType.PROCESS,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.QUEUED,
    )
    configuration = models.JSONField(default=dict)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.job_type} {self.document_id} ({self.status})"


class VectorIndexVersion(models.Model):
    class Status(models.TextChoices):
        BUILDING = "building", "Building"
        VALIDATING = "validating", "Validating"
        ACTIVE = "active", "Active"
        FAILED = "failed", "Failed"
        RETIRED = "retired", "Retired"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    collection_name = models.CharField(max_length=120, unique=True)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.BUILDING
    )
    provider = models.CharField(max_length=40)
    model_name = models.CharField(max_length=200)
    model_identity = models.CharField(max_length=300)
    vector_dimension = models.PositiveIntegerField()
    distance_metric = models.CharField(max_length=20, default="cosine")
    normalization = models.CharField(max_length=100)
    corpus_fingerprint = models.CharField(max_length=64, db_index=True)
    configuration = models.JSONField(default=dict)
    eligible_chunk_count = models.PositiveIntegerField(default=0)
    indexed_chunk_count = models.PositiveIntegerField(default=0)
    failure_detail = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["status"],
                condition=models.Q(status="active"),
                name="one_active_vector_index",
            )
        ]

    def __str__(self) -> str:
        return f"{self.collection_name} ({self.status})"


class ChunkEmbeddingRecord(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    index_version = models.ForeignKey(
        VectorIndexVersion, on_delete=models.PROTECT, related_name="embedding_records"
    )
    chunk = models.ForeignKey(
        DocumentChunk, on_delete=models.PROTECT, related_name="embedding_records"
    )
    vector_point_id = models.UUIDField()
    source_content_hash = models.CharField(max_length=64)
    embedding_input_hash = models.CharField(max_length=64)
    model_identity = models.CharField(max_length=300)
    vector_dimension = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["index_version", "chunk"], name="unique_chunk_per_vector_index"
            ),
            models.UniqueConstraint(
                fields=["index_version", "vector_point_id"],
                name="unique_point_per_vector_index",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.chunk_id} in {self.index_version_id}"
