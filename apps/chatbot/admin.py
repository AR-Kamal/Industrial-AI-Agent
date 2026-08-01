from django.contrib import admin

from .models import Conversation, Message


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = (
        "created_at",
        "answer_status",
        "citations",
        "generation_diagnostics",
    )


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "title", "created_at", "updated_at")
    list_filter = ("created_at", "updated_at")
    search_fields = ("title", "user__username")
    readonly_fields = ("created_at", "updated_at")
    inlines = (MessageInline,)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "conversation",
        "role",
        "status",
        "provider",
        "model_name",
        "answer_status",
        "safety_related",
        "created_at",
    )
    list_filter = (
        "role",
        "status",
        "answer_status",
        "safety_related",
        "provider",
        "created_at",
    )
    search_fields = ("content", "conversation__title", "conversation__user__username")
    readonly_fields = (
        "created_at",
        "answer_status",
        "citations",
        "safety_related",
        "index_version_id",
        "generation_diagnostics",
    )
