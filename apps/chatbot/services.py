"""Chat orchestration independent of HTTP and provider details."""

import logging
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.db.models import QuerySet
from django.utils import timezone

from apps.ai_gateway.errors import LLMGatewayError
from apps.ai_gateway.gateway import get_text_gateway
from apps.ai_gateway.services import ChatMessage
from apps.safety.prompts import (
    LIVE_MACHINE_DISCLAIMER,
    MANUFACTURING_ASSISTANT_SYSTEM_PROMPT,
    SAFETY_REFUSAL,
    UNSAFE_OUTPUT_FALLBACK,
)
from apps.safety.services import (
    ManufacturingSafetyControl,
    SafetyDisposition,
    implies_live_machine_access,
)

from .models import Conversation, Message

logger = logging.getLogger(__name__)

PROVIDER_ERROR_MESSAGES = {
    "configuration_error": "The local model configuration is invalid.",
    "provider_unavailable": (
        "The local Ollama service is unavailable. Start Ollama and try again."
    ),
    "model_not_installed": (
        "The configured local model is not installed. Pull the model and try again."
    ),
    "timeout": "The local model took too long to respond. Please try again.",
    "empty_response": "The local model returned an empty response. Please try again.",
    "malformed_response": (
        "The local model returned an unreadable response. Please try again."
    ),
    "unexpected_provider_error": (
        "The local model request failed unexpectedly. Please try again."
    ),
    "provider_error": "The local model request could not be completed.",
}


@dataclass(frozen=True)
class ChatTurn:
    conversation: Conversation
    user_message: Message
    assistant_message: Message


class ChatService:
    def __init__(
        self, safety_control: ManufacturingSafetyControl | None = None
    ) -> None:
        self.safety_control = safety_control or ManufacturingSafetyControl()

    def submit(
        self,
        *,
        user: User,
        content: str,
        conversation: Conversation | None = None,
    ) -> ChatTurn:
        conversation = conversation or Conversation.objects.create(
            user=user,
            title=content[:80],
        )
        user_message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=content,
        )

        request_safety = self.safety_control.evaluate_request(content)
        if request_safety.disposition == SafetyDisposition.STOP_AND_ESCALATE:
            assistant_message = self._store_assistant(
                conversation=conversation,
                content=SAFETY_REFUSAL,
                status=Message.Status.BLOCKED,
                provider="safety",
            )
            return ChatTurn(conversation, user_message, assistant_message)

        try:
            gateway = get_text_gateway()
            result = gateway.generate(self._build_context(conversation))
            response_text = result.text
            response_safety = self.safety_control.evaluate(response_text)
            if response_safety.disposition == SafetyDisposition.STOP_AND_ESCALATE:
                response_text = UNSAFE_OUTPUT_FALLBACK
                status = Message.Status.BLOCKED
            else:
                status = Message.Status.COMPLETE

            if (
                implies_live_machine_access(content)
                and "not connected to the machine" not in response_text.lower()
            ):
                response_text = f"{LIVE_MACHINE_DISCLAIMER}\n\n{response_text}"

            assistant_message = self._store_assistant(
                conversation=conversation,
                content=response_text,
                status=status,
                provider=result.provider,
                model_name=result.model,
            )
        except LLMGatewayError as exc:
            logger.warning(
                "LLM request failed",
                extra={"error_code": exc.code, "conversation_id": conversation.pk},
            )
            assistant_message = self._store_assistant(
                conversation=conversation,
                content=PROVIDER_ERROR_MESSAGES.get(
                    exc.code,
                    PROVIDER_ERROR_MESSAGES["provider_error"],
                ),
                status=Message.Status.ERROR,
                error_code=exc.code,
            )

        return ChatTurn(conversation, user_message, assistant_message)

    @staticmethod
    def _build_context(conversation: Conversation) -> tuple[ChatMessage, ...]:
        history: QuerySet[Message] = conversation.messages.filter(
            status=Message.Status.COMPLETE,
        ).order_by("-created_at", "-pk")[:10]
        messages = [
            ChatMessage(role=message.role, content=message.content)
            for message in reversed(list(history))
            if message.role in {Message.Role.USER, Message.Role.ASSISTANT}
        ]
        return (
            ChatMessage(
                role="system",
                content=MANUFACTURING_ASSISTANT_SYSTEM_PROMPT,
            ),
            *messages,
        )

    @staticmethod
    def _store_assistant(
        *,
        conversation: Conversation,
        content: str,
        status: str,
        provider: str = "",
        model_name: str = "",
        error_code: str = "",
    ) -> Message:
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=content,
            status=status,
            provider=provider,
            model_name=model_name,
            error_code=error_code,
        )
        Conversation.objects.filter(pk=conversation.pk).update(
            updated_at=timezone.now()
        )
        return message
