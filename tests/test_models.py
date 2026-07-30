import pytest
from django.contrib.auth import get_user_model

from apps.chatbot.models import Conversation, Message


@pytest.mark.django_db
def test_conversation_creation() -> None:
    user = get_user_model().objects.create_user(username="developer")

    conversation = Conversation.objects.create(
        user=user,
        title="Robot alarm question",
    )

    assert conversation.pk is not None
    assert conversation.user == user
    assert str(conversation) == "Robot alarm question"


@pytest.mark.django_db
def test_message_storage() -> None:
    user = get_user_model().objects.create_user(username="developer")
    conversation = Conversation.objects.create(user=user)

    message = Message.objects.create(
        conversation=conversation,
        role=Message.Role.USER,
        content="What does this alarm mean?",
    )

    stored = conversation.messages.get()
    assert stored == message
    assert stored.role == Message.Role.USER
    assert stored.content == "What does this alarm mean?"
