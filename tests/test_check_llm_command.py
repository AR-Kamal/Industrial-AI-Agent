from io import StringIO
from unittest.mock import Mock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.ai_gateway.errors import ProviderUnavailableError
from apps.ai_gateway.services import ProviderHealth


def test_check_llm_command_reports_ready_provider() -> None:
    gateway = Mock()
    gateway.health_check.return_value = ProviderHealth(
        provider="ollama",
        model="test-model",
        available=True,
        detail="ready",
    )
    stdout = StringIO()

    with patch(
        "apps.ai_gateway.management.commands.check_llm.get_text_gateway",
        return_value=gateway,
    ):
        call_command("check_llm", stdout=stdout)

    assert "Local LLM ready" in stdout.getvalue()
    assert "test-model" in stdout.getvalue()


def test_check_llm_command_returns_controlled_error() -> None:
    gateway = Mock()
    gateway.health_check.side_effect = ProviderUnavailableError()
    stderr = StringIO()

    with (
        patch(
            "apps.ai_gateway.management.commands.check_llm.get_text_gateway",
            return_value=gateway,
        ),
        pytest.raises(CommandError) as exc_info,
    ):
        call_command("check_llm", stderr=stderr)

    assert "provider_unavailable" in str(exc_info.value)
