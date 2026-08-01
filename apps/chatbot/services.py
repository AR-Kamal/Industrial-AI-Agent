"""Chat orchestration independent of HTTP and provider details."""

import logging
from dataclasses import dataclass

from django.contrib.auth.models import User
from django.utils import timezone

from apps.safety.prompts import (
    SAFETY_REFUSAL,
)
from apps.safety.services import (
    ManufacturingSafetyControl,
    SafetyDisposition,
)

from .grounded import (
    AnswerStatus,
    GroundedAnswerRequest,
    GroundedAnswerService,
    citation_dicts,
)
from .models import Conversation, Message

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ChatTurn:
    conversation: Conversation
    user_message: Message
    assistant_message: Message


class ChatService:
    def __init__(
        self,
        safety_control: ManufacturingSafetyControl | None = None,
        grounded_service: GroundedAnswerService | None = None,
    ) -> None:
        self.safety_control = safety_control or ManufacturingSafetyControl()
        self.grounded_service = grounded_service or GroundedAnswerService(
            safety_control=self.safety_control
        )

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

        result = self.grounded_service.answer(GroundedAnswerRequest(content))
        message_status = {
            AnswerStatus.ANSWERED: Message.Status.COMPLETE,
            AnswerStatus.CONVERSATIONAL: Message.Status.COMPLETE,
            AnswerStatus.SAFETY_REFUSAL: Message.Status.BLOCKED,
            AnswerStatus.GENERATION_ERROR: Message.Status.ERROR,
        }.get(result.status, Message.Status.ABSTAINED)
        diagnostics = result.diagnostics.__dict__ if result.diagnostics else {}
        assistant_message = self._store_assistant(
            conversation=conversation,
            content=result.answer,
            status=message_status,
            provider=result.provider,
            model_name=result.model,
            error_code=result.error_code,
            answer_status=result.status,
            citations=citation_dicts(result, staff=True),
            safety_related=result.safety_related,
            index_version_id=(
                result.diagnostics.active_index_id if result.diagnostics else ""
            ),
            diagnostics=diagnostics,
        )

        return ChatTurn(conversation, user_message, assistant_message)

    @staticmethod
    def _store_assistant(
        *,
        conversation: Conversation,
        content: str,
        status: str,
        provider: str = "",
        model_name: str = "",
        error_code: str = "",
        answer_status: str = "",
        citations: list[dict[str, object]] | None = None,
        safety_related: bool = False,
        index_version_id: str = "",
        diagnostics: dict[str, object] | None = None,
    ) -> Message:
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=content,
            status=status,
            provider=provider,
            model_name=model_name,
            error_code=error_code,
            answer_status=answer_status,
            citations=citations or [],
            safety_related=safety_related,
            index_version_id=index_version_id,
            generation_diagnostics=diagnostics or {},
        )
        Conversation.objects.filter(pk=conversation.pk).update(
            updated_at=timezone.now()
        )
        return message
