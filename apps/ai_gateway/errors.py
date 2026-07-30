"""Safe, provider-neutral gateway exceptions."""


class LLMGatewayError(Exception):
    """Base exception safe for application-level classification."""

    code = "provider_error"


class ProviderConfigurationError(LLMGatewayError):
    code = "configuration_error"


class ProviderUnavailableError(LLMGatewayError):
    code = "provider_unavailable"


class ModelNotInstalledError(LLMGatewayError):
    code = "model_not_installed"


class ProviderTimeoutError(LLMGatewayError):
    code = "timeout"


class EmptyResponseError(LLMGatewayError):
    code = "empty_response"


class MalformedResponseError(LLMGatewayError):
    code = "malformed_response"


class UnexpectedProviderError(LLMGatewayError):
    code = "unexpected_provider_error"
