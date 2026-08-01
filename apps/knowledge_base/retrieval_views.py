from django import forms
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .retrieval import RetrievedChunk, retrieve
from .runtime import embedding_provider, vector_store


class RetrievalInspectionForm(forms.Form):
    query = forms.CharField(max_length=1000)
    top_k = forms.IntegerField(
        min_value=1, max_value=settings.RETRIEVAL_MAX_TOP_K, initial=5
    )
    mode = forms.ChoiceField(
        choices=(("dense", "Dense"), ("safety_first", "Safety first"))
    )
    document_id = forms.CharField(max_length=100, required=False)


@staff_member_required
def retrieval_inspection(request: HttpRequest) -> HttpResponse:
    form = RetrievalInspectionForm(request.GET or None)
    results: list[RetrievedChunk] = []
    error = ""
    if form.is_valid():
        try:
            with vector_store() as store:
                results = retrieve(
                    form.cleaned_data["query"],
                    embedding_provider(),
                    store,
                    top_k=form.cleaned_data["top_k"],
                    max_top_k=settings.RETRIEVAL_MAX_TOP_K,
                    minimum_score=settings.RETRIEVAL_MIN_SCORE,
                    safety_first=form.cleaned_data["mode"] == "safety_first",
                    document_id=form.cleaned_data["document_id"] or None,
                )
        except Exception as exc:
            error = f"Retrieval unavailable ({type(exc).__name__})."
    return render(
        request,
        "knowledge_base/retrieval_inspection.html",
        {"form": form, "results": results, "error": error},
    )
