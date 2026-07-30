"""Staff forms for previewing and applying chunk corrections."""

from django import forms

from .corrections import SPLIT_MARKER


class ChunkSplitDefinitionForm(forms.Form):
    marked_content = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 28, "style": "width: 100%;"}),
        help_text=f"Insert a line containing {SPLIT_MARKER} at each split point.",
    )


class ChunkSplitSegmentForm(forms.Form):
    content = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 12, "style": "width: 100%;"})
    )
    chapter = forms.CharField(max_length=300, required=False)
    section = forms.CharField(max_length=300, required=False)
    page_start = forms.IntegerField(min_value=1, required=False)
    page_end = forms.IntegerField(min_value=1, required=False)
    contains_warning = forms.BooleanField(required=False)
    contains_caution = forms.BooleanField(required=False)
    retrieval_enabled = forms.BooleanField(
        required=False,
        initial=True,
        help_text="Enable only when this child is ready for future retrieval.",
    )
    reviewer_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "style": "width: 100%;"}),
    )


class ChunkSplitApplyForm(forms.Form):
    source_content_hash = forms.CharField(widget=forms.HiddenInput)
    marked_content = forms.CharField(widget=forms.HiddenInput)
    artifact_note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 3, "style": "width: 100%;"}),
        help_text="Required if source text was removed or corrected.",
    )
    safety_confirmed = forms.BooleanField(
        required=False,
        label=(
            "I confirmed warnings, cautions, procedures, prerequisites, exceptions, "
            "and table notes remain with their applicable content."
        ),
    )
