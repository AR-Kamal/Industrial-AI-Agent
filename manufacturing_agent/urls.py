"""Root URL configuration."""

from django.contrib import admin
from django.urls import include, path

from apps.accounts.views import logout_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/logout/", logout_view, name="logout"),
    path("accounts/", include("django.contrib.auth.urls")),
    path("chat/", include("apps.chatbot.urls")),
    path("", include("apps.accounts.urls")),
]
