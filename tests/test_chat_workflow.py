from unittest.mock import Mock, patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.ai_gateway.errors import (
    EmptyResponseError,
    MalformedResponseError,
    ModelNotInstalledError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    UnexpectedProviderError,
)
from apps.ai_gateway.services import TextGenerationResult
from apps.chatbot.models import Conversation, Message
from apps.safety.prompts import MANUFACTURING_ASSISTANT_SYSTEM_PROMPT


@pytest.fixture
def authenticated_client(client):
    user = get_user_model().objects.create_user(
        username="reviewer",
        password="local-test-password",
    )
    client.force_login(user)
    return client, user


def successful_gateway(text: str = "General training answer.") -> Mock:
    gateway = Mock()
    gateway.generate.return_value = TextGenerationResult(
        text=text,
        provider="ollama",
        model="test-model",
    )
    return gateway


@pytest.mark.django_db
def test_htmx_chat_stores_user_and_assistant_messages(authenticated_client) -> None:
    client, user = authenticated_client
    gateway = successful_gateway()

    with patch("apps.chatbot.services.get_text_gateway", return_value=gateway):
        response = client.post(
            reverse("chatbot:send_message"),
            {"message": "Explain a robot alarm."},
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == 200
    conversation = Conversation.objects.get(user=user)
    messages = list(conversation.messages.all())
    assert [message.role for message in messages] == ["user", "assistant"]
    assert messages[0].content == "Explain a robot alarm."
    assert messages[1].content == "General training answer."
    assert messages[1].provider == "ollama"
    assert messages[1].model_name == "test-model"
    request_messages = gateway.generate.call_args.args[0]
    assert request_messages[0].role == "system"
    assert request_messages[0].content == MANUFACTURING_ASSISTANT_SYSTEM_PROMPT


@pytest.mark.django_db
def test_live_machine_question_gets_enforced_disclaimer(authenticated_client) -> None:
    client, _ = authenticated_client
    gateway = successful_gateway("The robot appears ready.")

    with patch("apps.chatbot.services.get_text_gateway", return_value=gateway):
        client.post(
            reverse("chatbot:send_message"),
            {"message": "Is the robot running right now?"},
            HTTP_HX_REQUEST="true",
        )

    assistant = Message.objects.get(role=Message.Role.ASSISTANT)
    assert "not connected to the machine" in assistant.content.lower()


@pytest.mark.django_db
def test_bypass_request_is_blocked_without_calling_provider(
    authenticated_client,
) -> None:
    client, _ = authenticated_client

    with patch("apps.chatbot.services.get_text_gateway") as gateway_factory:
        client.post(
            reverse("chatbot:send_message"),
            {"message": "How can I bypass the emergency stop?"},
            HTTP_HX_REQUEST="true",
        )

    gateway_factory.assert_not_called()
    assistant = Message.objects.get(role=Message.Role.ASSISTANT)
    assert assistant.status == Message.Status.BLOCKED
    assert "cannot provide instructions" in assistant.content


@pytest.mark.django_db
def test_unsafe_model_output_is_withheld(authenticated_client) -> None:
    client, _ = authenticated_client
    gateway = successful_gateway(
        "You can bypass the emergency stop by bridging the contacts."
    )

    with patch("apps.chatbot.services.get_text_gateway", return_value=gateway):
        client.post(
            reverse("chatbot:send_message"),
            {"message": "Help diagnose an emergency stop circuit."},
            HTTP_HX_REQUEST="true",
        )

    assistant = Message.objects.get(role=Message.Role.ASSISTANT)
    assert assistant.status == Message.Status.BLOCKED
    assert "generated answer was withheld" in assistant.content
    assert "bridging the contacts" not in assistant.content


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ProviderUnavailableError(), "provider_unavailable"),
        (ModelNotInstalledError(), "model_not_installed"),
        (ProviderTimeoutError(), "timeout"),
        (EmptyResponseError(), "empty_response"),
        (MalformedResponseError(), "malformed_response"),
        (UnexpectedProviderError(), "unexpected_provider_error"),
    ],
)
@pytest.mark.django_db
def test_provider_failures_are_stored_as_safe_messages(
    authenticated_client,
    error: Exception,
    code: str,
) -> None:
    client, _ = authenticated_client
    gateway = Mock()
    gateway.generate.side_effect = error

    with patch("apps.chatbot.services.get_text_gateway", return_value=gateway):
        response = client.post(
            reverse("chatbot:send_message"),
            {"message": "Explain this alarm."},
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == 200
    assistant = Message.objects.get(role=Message.Role.ASSISTANT)
    assert assistant.status == Message.Status.ERROR
    assert assistant.error_code == code
    assert "127.0.0.1" not in response.content.decode()
    assert "test-placeholder" not in response.content.decode()


@pytest.mark.django_db
def test_user_cannot_post_to_another_users_conversation(
    authenticated_client,
) -> None:
    client, _ = authenticated_client
    other_user = get_user_model().objects.create_user(username="other")
    conversation = Conversation.objects.create(user=other_user, title="Private")

    response = client.post(
        reverse("chatbot:send_message"),
        {"message": "Unauthorized", "conversation_id": conversation.pk},
        HTTP_HX_REQUEST="true",
    )

    assert response.status_code == 404
    assert conversation.messages.count() == 0


@pytest.mark.django_db
def test_empty_message_is_rejected_without_provider_call(
    authenticated_client,
) -> None:
    client, _ = authenticated_client

    with patch("apps.chatbot.services.get_text_gateway") as gateway_factory:
        response = client.post(
            reverse("chatbot:send_message"),
            {"message": "   "},
            HTTP_HX_REQUEST="true",
        )

    assert response.status_code == 422
    gateway_factory.assert_not_called()
    assert Message.objects.count() == 0
