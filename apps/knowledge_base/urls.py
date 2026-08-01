from django.urls import path

from .retrieval_views import retrieval_inspection

app_name = "knowledge_base"

urlpatterns = [
    path("retrieval/", retrieval_inspection, name="retrieval_inspection"),
]
