"""Gateway provider construction."""

from .config import get_llm_config
from .providers.ollama import OllamaProvider
from .services import LLMProvider


def get_llm_provider() -> LLMProvider:
    config = get_llm_config()
    return OllamaProvider(config)
