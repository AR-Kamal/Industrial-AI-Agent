import hashlib
import re
from pathlib import Path
from typing import Any

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import QuerySet
from django.forms import formset_factory
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from .corrections import (
    SplitSegment,
    apply_split,
    boundary_requires_confirmation,
    split_marker_parts,
)
from .exceptions import KnowledgeBaseError
from .forms import (
    ChunkSplitApplyForm,
    ChunkSplitDefinitionForm,
    ChunkSplitSegmentForm,
)
from .ingestion import process_document
from .models import (
    ChunkEmbeddingRecord,
    ChunkMetadataCorrection,
    ChunkReplacementCorrection,
    ChunkSplitCorrection,
    DocumentChunk,
    DocumentVersion,
    IngestionJob,
    KnowledgeDocument,
    VectorIndexVersion,
)
from .validation import validate_uploaded_document

SPLIT_FORMSET_PREFIX = "segments"


class DocumentVersionInline(admin.TabularInline):
    model = DocumentVersion
    extra = 0
    fields = (
        "version_id",
        "version_or_edition",
        "source_file",
        "source_filename",
        "checksum",
        "file_size",
        "processed_at",
    )
    readonly_fields = (
        "version_id",
        "source_filename",
        "checksum",
        "file_size",
        "processed_at",
    )


@admin.register(KnowledgeDocument)
class KnowledgeDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "document_id",
        "title",
        "manufacturer",
        "document_type",
        "approval_status",
        "lifecycle_status",
        "processing_status",
        "safety_priority",
        "verification_status",
        "preview_link",
    )
    list_filter = (
        "approval_status",
        "lifecycle_status",
        "processing_status",
        "safety_priority",
        "current_version_verification_status",
        "manufacturer",
        "document_type",
    )
    search_fields = (
        "document_id",
        "title",
        "document_code",
        "manufacturer",
        "equipment_family",
        "equipment_model",
    )
    readonly_fields = (
        "checksum",
        "processing_status",
        "processing_date",
        "created_at",
        "updated_at",
    )
    inlines = (DocumentVersionInline,)
    actions = (
        "mark_under_review",
        "approve_documents",
        "reject_documents",
        "process_approved_documents",
    )

    fieldsets = (
        (
            "Identity",
            {
                "fields": (
                    "document_id",
                    "title",
                    "document_code",
                    "document_type",
                    "manufacturer",
                    "equipment_family",
                    "equipment_model",
                    "subsystem",
                    "language",
                )
            },
        ),
        (
            "Version and governance",
            {
                "fields": (
                    "version_or_edition",
                    "revision_or_effective_date",
                    "revision_label",
                    "approval_status",
                    "lifecycle_status",
                    "current_version_verification_status",
                    "approved_by",
                    "access_level",
                    "safety_priority",
                )
            },
        ),
        (
            "Processing",
            {
                "fields": (
                    "source_filename",
                    "checksum",
                    "processing_status",
                    "processing_date",
                    "notes",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_urls(self) -> list:
        urls = super().get_urls()
        custom = [
            path(
                "<path:object_id>/preview/",
                self.admin_site.admin_view(self.preview_view),
                name="knowledge_base_knowledgedocument_preview",
            )
        ]
        return custom + urls

    def preview_view(
        self,
        request: HttpRequest,
        object_id: str,
    ) -> HttpResponse:
        document = get_object_or_404(
            KnowledgeDocument.objects.prefetch_related(
                "versions",
                "chunks",
                "ingestion_jobs",
            ),
            pk=object_id,
        )
        version = document.versions.first()
        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "document": document,
            "version": version,
            "chunks": document.chunks.select_related("document_version"),
            "jobs": document.ingestion_jobs.all()[:10],
            "title": f"Preview {document.document_id}",
        }
        return render(
            request,
            "admin/knowledge_base/document_preview.html",
            context,
        )

    @admin.display(description="Version status")
    def verification_status(self, obj: KnowledgeDocument) -> str:
        return obj.get_current_version_verification_status_display()

    @admin.display(description="Preview")
    def preview_link(self, obj: KnowledgeDocument) -> str:
        url = reverse(
            "admin:knowledge_base_knowledgedocument_preview",
            args=[obj.pk],
        )
        return format_html('<a href="{}">Inspect</a>', url)

    @admin.action(description="Mark selected documents under review")
    def mark_under_review(
        self, request: HttpRequest, queryset: QuerySet[KnowledgeDocument]
    ) -> None:
        queryset.update(
            approval_status=KnowledgeDocument.ApprovalStatus.PENDING,
            lifecycle_status=KnowledgeDocument.LifecycleStatus.UNDER_REVIEW,
            approved_by=None,
        )

    @admin.action(description="Approve selected documents for processing")
    def approve_documents(
        self, request: HttpRequest, queryset: QuerySet[KnowledgeDocument]
    ) -> None:
        count = queryset.update(
            approval_status=KnowledgeDocument.ApprovalStatus.APPROVED,
            lifecycle_status=KnowledgeDocument.LifecycleStatus.APPROVED,
            approved_by=request.user,
        )
        self.message_user(request, f"Approved {count} document(s).")

    @admin.action(description="Reject selected documents")
    def reject_documents(
        self, request: HttpRequest, queryset: QuerySet[KnowledgeDocument]
    ) -> None:
        count = queryset.update(
            approval_status=KnowledgeDocument.ApprovalStatus.REJECTED,
            lifecycle_status=KnowledgeDocument.LifecycleStatus.REJECTED,
        )
        self.message_user(request, f"Rejected {count} document(s).")

    @admin.action(description="Process selected approved documents")
    def process_approved_documents(
        self, request: HttpRequest, queryset: QuerySet[KnowledgeDocument]
    ) -> None:
        completed = 0
        for document in queryset:
            try:
                process_document(document.pk)
                completed += 1
            except KnowledgeBaseError as exc:
                self.message_user(
                    request,
                    f"{document.pk}: {exc}",
                    level=messages.ERROR,
                )
        if completed:
            self.message_user(request, f"Processed {completed} document(s).")


@admin.register(DocumentVersion)
class DocumentVersionAdmin(admin.ModelAdmin):
    class DocumentVersionForm(forms.ModelForm):
        class Meta:
            model = DocumentVersion
            fields = (
                "document",
                "version_or_edition",
                "revision_or_effective_date",
                "revision_label",
                "source_file",
            )

        def clean_source_file(self) -> object:
            source_file = self.cleaned_data["source_file"]
            try:
                _, media_type, size, checksum = validate_uploaded_document(
                    source_file.file,
                    source_file.name,
                )
            except KnowledgeBaseError as exc:
                raise forms.ValidationError(str(exc)) from exc
            duplicate = DocumentVersion.objects.filter(checksum=checksum)
            if self.instance.pk:
                duplicate = duplicate.exclude(pk=self.instance.pk)
            if duplicate.exists():
                raise forms.ValidationError(
                    "An identical document version is already registered."
                )
            source_file._knowledge_validation = (media_type, size, checksum)
            return source_file

    form = DocumentVersionForm
    list_display = (
        "version_id",
        "document",
        "source_filename",
        "file_size",
        "page_count",
        "processed_at",
    )
    search_fields = (
        "version_id",
        "document__document_id",
        "document__title",
        "source_filename",
        "checksum",
    )
    readonly_fields = (
        "version_id",
        "checksum",
        "file_size",
        "media_type",
        "extracted_text",
        "page_count",
        "extraction_warnings",
        "extraction_errors",
        "created_at",
        "processed_at",
    )

    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: DocumentVersion | None = None,
    ) -> tuple[str, ...]:
        if obj is None:
            return ("created_at", "processed_at")
        return self.readonly_fields

    def save_model(
        self,
        request: HttpRequest,
        obj: DocumentVersion,
        form: forms.ModelForm,
        change: bool,
    ) -> None:
        if not change:
            source_file = form.cleaned_data["source_file"]
            media_type, size, checksum = source_file._knowledge_validation
            obj.source_filename = Path(source_file.name).name
            obj.media_type = media_type
            obj.file_size = size
            obj.checksum = checksum
            edition = (
                obj.version_or_edition
                or obj.document.version_or_edition
                or "unversioned"
            )
            normalized = "".join(
                character if character.isalnum() else "-" for character in edition
            ).strip("-")
            material = f"{obj.document_id}|{edition}|{checksum}".encode()
            obj.version_id = (
                f"{obj.document_id}-{normalized}-"
                f"{hashlib.sha256(material).hexdigest()[:12]}"
            )
        super().save_model(request, obj, form, change)
        if not change:
            document = obj.document
            document.source_filename = obj.source_filename
            document.checksum = obj.checksum
            document.lifecycle_status = KnowledgeDocument.LifecycleStatus.UNDER_REVIEW
            document.processing_status = (
                KnowledgeDocument.ProcessingStatus.NOT_PROCESSED
            )
            document.save(
                update_fields=[
                    "source_filename",
                    "checksum",
                    "lifecycle_status",
                    "processing_status",
                    "updated_at",
                ]
            )


@admin.register(DocumentChunk)
class DocumentChunkAdmin(admin.ModelAdmin):
    list_display = (
        "chunk_id",
        "document",
        "sequence",
        "chapter",
        "section",
        "page_range",
        "token_count",
        "contains_warning",
        "contains_caution",
        "origin",
        "retrieval_enabled",
        "review_status",
        "split_link",
    )
    list_filter = (
        "review_status",
        "contains_warning",
        "contains_caution",
        "origin",
        "retrieval_enabled",
        "is_current_generation",
        "safety_priority",
        "manufacturer",
    )
    search_fields = (
        "chunk_id",
        "document__document_id",
        "chapter",
        "section",
        "content",
    )
    readonly_fields = (
        "chunk_id",
        "document",
        "document_version",
        "sequence",
        "content",
        "content_hash",
        "chapter",
        "section",
        "page_start",
        "page_end",
        "manufacturer",
        "equipment_family",
        "subsystem",
        "safety_priority",
        "token_count",
        "contains_warning",
        "contains_caution",
        "origin",
        "parent_chunk",
        "retrieval_enabled",
        "is_current_generation",
        "review_status",
        "processing_warnings",
        "duplicate_of",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    actions = (
        "mark_approved",
        "mark_requires_correction",
        "exclude_from_retrieval",
        "split_chunk",
    )

    def get_urls(self) -> list[Any]:
        return [
            path(
                "<path:object_id>/split/",
                self.admin_site.admin_view(self.split_view),
                name="knowledge_base_documentchunk_split",
            )
        ] + super().get_urls()

    @admin.display(description="Correction")
    def split_link(self, obj: DocumentChunk) -> str:
        if (
            obj.origin != DocumentChunk.Origin.GENERATED
            or not obj.is_current_generation
            or obj.review_status == DocumentChunk.ReviewStatus.SUPERSEDED
        ):
            return "—"
        url = reverse("admin:knowledge_base_documentchunk_split", args=[obj.pk])
        return format_html('<a href="{}">Split chunk</a>', url)

    @admin.action(description="Split chunk")
    def split_chunk(
        self, request: HttpRequest, queryset: QuerySet[DocumentChunk]
    ) -> HttpResponseRedirect | None:
        if queryset.count() != 1:
            self.message_user(
                request,
                "Select exactly one generated chunk to split.",
                level=messages.ERROR,
            )
            return None
        selected = queryset.first()
        if selected is None:
            return None
        return redirect(
            "admin:knowledge_base_documentchunk_split",
            object_id=selected.pk,
        )

    def split_view(self, request: HttpRequest, object_id: str) -> HttpResponse:
        source = get_object_or_404(
            DocumentChunk.objects.select_related("document", "document_version"),
            pk=object_id,
        )
        if not self.has_change_permission(request, source):
            raise PermissionDenied
        if (
            source.origin != DocumentChunk.Origin.GENERATED
            or not source.is_current_generation
            or source.review_status == DocumentChunk.ReviewStatus.SUPERSEDED
        ):
            self.message_user(
                request,
                "Only a current, unsuperseded generated chunk can be split.",
                level=messages.ERROR,
            )
            return redirect("admin:knowledge_base_documentchunk_change", source.pk)

        segment_formset_class = formset_factory(
            ChunkSplitSegmentForm,
            extra=0,
            min_num=2,
            validate_min=True,
        )
        definition_form = ChunkSplitDefinitionForm(
            initial={"marked_content": source.content}
        )
        apply_form: ChunkSplitApplyForm | None = None
        segment_formset = None
        safety_required = False

        if request.method == "POST" and request.POST.get("stage") == "preview":
            definition_form = ChunkSplitDefinitionForm(request.POST)
            if definition_form.is_valid():
                marked_content = definition_form.cleaned_data["marked_content"]
                try:
                    parts = split_marker_parts(marked_content)
                except ValidationError as exc:
                    definition_form.add_error("marked_content", exc)
                else:
                    safety_required = boundary_requires_confirmation(marked_content)
                    initial = [
                        {
                            "content": part,
                            "chapter": source.chapter,
                            "section": source.section,
                            "page_start": source.page_start,
                            "page_end": source.page_end,
                            "contains_warning": bool(
                                re.search(r"\bwarning\b", part, re.IGNORECASE)
                            ),
                            "contains_caution": bool(
                                re.search(r"\bcaution\b", part, re.IGNORECASE)
                            ),
                            "retrieval_enabled": True,
                        }
                        for part in parts
                    ]
                    segment_formset = segment_formset_class(
                        initial=initial,
                        prefix=SPLIT_FORMSET_PREFIX,
                    )
                    apply_form = ChunkSplitApplyForm(
                        initial={
                            "source_content_hash": source.content_hash,
                            "marked_content": marked_content,
                        }
                    )

        if request.method == "POST" and request.POST.get("stage") == "apply":
            apply_form = ChunkSplitApplyForm(request.POST)
            segment_formset = segment_formset_class(
                request.POST,
                prefix=SPLIT_FORMSET_PREFIX,
            )
            marked_content = request.POST.get("marked_content", "")
            safety_required = boundary_requires_confirmation(marked_content)
            apply_valid = apply_form.is_valid()
            segments_valid = segment_formset.is_valid()
            if apply_valid and segments_valid:
                if (
                    apply_form.cleaned_data["source_content_hash"]
                    != source.content_hash
                ):
                    apply_form.add_error(
                        None,
                        "The source chunk changed. Preview the split again.",
                    )
                else:
                    segments = [
                        SplitSegment(**form.cleaned_data)
                        for form in segment_formset
                        if form.cleaned_data
                    ]
                    try:
                        correction = apply_split(
                            source,
                            segments,
                            reviewer=request.user,
                            artifact_note=apply_form.cleaned_data["artifact_note"],
                            safety_confirmed=apply_form.cleaned_data[
                                "safety_confirmed"
                            ],
                            safety_confirmation_required=safety_required,
                        )
                    except ValidationError as exc:
                        apply_form.add_error(None, exc)
                    else:
                        self.message_user(
                            request,
                            f"Created {len(segments)} correction children "
                            f"under {correction.id}.",
                            level=messages.SUCCESS,
                        )
                        return redirect("admin:knowledge_base_documentchunk_changelist")
            elif (
                f"{SPLIT_FORMSET_PREFIX}-TOTAL_FORMS" not in request.POST
                or f"{SPLIT_FORMSET_PREFIX}-INITIAL_FORMS" not in request.POST
            ):
                indices = sorted(
                    {
                        int(match.group(1))
                        for key in request.POST
                        if (
                            match := re.fullmatch(
                                rf"{SPLIT_FORMSET_PREFIX}-(\d+)-content",
                                key,
                            )
                        )
                    }
                )
                recovered = []
                for index in indices:
                    prefix = f"{SPLIT_FORMSET_PREFIX}-{index}"
                    recovered.append(
                        {
                            name: request.POST.get(f"{prefix}-{name}", "")
                            for name in (
                                "content",
                                "chapter",
                                "section",
                                "page_start",
                                "page_end",
                                "reviewer_notes",
                            )
                        }
                        | {
                            name: f"{prefix}-{name}" in request.POST
                            for name in (
                                "contains_warning",
                                "contains_caution",
                                "retrieval_enabled",
                            )
                        }
                    )
                segment_formset = segment_formset_class(
                    initial=recovered,
                    prefix=SPLIT_FORMSET_PREFIX,
                )
                apply_form.add_error(
                    None,
                    "The child form metadata was incomplete. "
                    "Your entered values are shown below; review and submit again.",
                )

        context = {
            **self.admin_site.each_context(request),
            "opts": self.model._meta,
            "source": source,
            "definition_form": definition_form,
            "apply_form": apply_form,
            "segment_formset": segment_formset,
            "safety_required": safety_required,
            "title": f"Split {source.chunk_id}",
        }
        return render(
            request,
            "admin/knowledge_base/documentchunk/split.html",
            context,
        )

    @admin.display(description="Pages")
    def page_range(self, obj: DocumentChunk) -> str:
        if obj.page_start is None:
            return "—"
        if obj.page_start == obj.page_end:
            return str(obj.page_start)
        return f"{obj.page_start}–{obj.page_end}"

    @admin.action(description="Mark selected chunks approved")
    def mark_approved(
        self, request: HttpRequest, queryset: QuerySet[DocumentChunk]
    ) -> None:
        queryset.exclude(review_status=DocumentChunk.ReviewStatus.SUPERSEDED).filter(
            is_current_generation=True
        ).update(
            review_status=DocumentChunk.ReviewStatus.APPROVED,
            retrieval_enabled=True,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    @admin.action(description="Mark selected chunks as requiring correction")
    def mark_requires_correction(
        self, request: HttpRequest, queryset: QuerySet[DocumentChunk]
    ) -> None:
        queryset.update(
            review_status=DocumentChunk.ReviewStatus.REQUIRES_CORRECTION,
            retrieval_enabled=False,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )

    @admin.action(description="Exclude selected chunks from retrieval")
    def exclude_from_retrieval(
        self, request: HttpRequest, queryset: QuerySet[DocumentChunk]
    ) -> None:
        queryset.update(
            review_status=DocumentChunk.ReviewStatus.EXCLUDED,
            retrieval_enabled=False,
            reviewed_by=request.user,
            reviewed_at=timezone.now(),
        )


@admin.register(ChunkSplitCorrection)
class ChunkSplitCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_chunk",
        "document_version",
        "status",
        "created_by",
        "created_at",
        "applied_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "id",
        "source_chunk__chunk_id",
        "document_version__version_id",
    )
    readonly_fields = (
        "id",
        "source_chunk",
        "source_content_hash",
        "document_version",
        "segment_payload",
        "artifact_changes",
        "status",
        "created_by",
        "created_at",
        "applied_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: ChunkSplitCorrection | None = None,
    ) -> bool:
        return request.user.has_perm("knowledge_base.view_chunksplitcorrection")

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: ChunkSplitCorrection | None = None,
    ) -> bool:
        return False


@admin.register(ChunkMetadataCorrection)
class ChunkMetadataCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "source_chunk",
        "created_by",
        "created_at",
    )
    search_fields = ("id", "source_chunk__chunk_id")
    readonly_fields = (
        "id",
        "source_chunk",
        "source_content_hash",
        "before_payload",
        "after_payload",
        "created_by",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: ChunkMetadataCorrection | None = None,
    ) -> bool:
        return request.user.has_perm("knowledge_base.view_chunkmetadatacorrection")

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: ChunkMetadataCorrection | None = None,
    ) -> bool:
        return False


@admin.register(ChunkReplacementCorrection)
class ChunkReplacementCorrectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "replaced_child",
        "replacement_child",
        "status",
        "reviewer",
        "created_at",
    )
    list_filter = ("status", "created_at")
    search_fields = (
        "id",
        "replaced_child__chunk_id",
        "replacement_child__chunk_id",
    )
    readonly_fields = (
        "id",
        "replaced_child",
        "replacement_child",
        "old_content_hash",
        "new_content_hash",
        "corrected_content",
        "reason",
        "reviewer_notes",
        "reviewer",
        "document",
        "document_version",
        "status",
        "created_at",
        "applied_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: ChunkReplacementCorrection | None = None,
    ) -> bool:
        return request.user.has_perm("knowledge_base.view_chunkreplacementcorrection")

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: ChunkReplacementCorrection | None = None,
    ) -> bool:
        return False


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "document",
        "job_type",
        "status",
        "chunk_count",
        "started_at",
        "completed_at",
    )
    list_filter = ("status", "job_type", "created_at")
    search_fields = ("id", "document__document_id", "document__title")
    readonly_fields = (
        "id",
        "document",
        "document_version",
        "job_type",
        "status",
        "configuration",
        "warnings",
        "errors",
        "chunk_count",
        "started_at",
        "completed_at",
        "created_at",
    )


@admin.register(VectorIndexVersion)
class VectorIndexVersionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "status",
        "model_identity",
        "vector_dimension",
        "indexed_chunk_count",
        "created_at",
    )
    readonly_fields = [field.name for field in VectorIndexVersion._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: VectorIndexVersion | None = None
    ) -> bool:
        return False


@admin.register(ChunkEmbeddingRecord)
class ChunkEmbeddingRecordAdmin(admin.ModelAdmin):
    list_display = (
        "chunk",
        "index_version",
        "vector_point_id",
        "model_identity",
        "created_at",
    )
    readonly_fields = [field.name for field in ChunkEmbeddingRecord._meta.fields]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(
        self, request: HttpRequest, obj: ChunkEmbeddingRecord | None = None
    ) -> bool:
        return False
