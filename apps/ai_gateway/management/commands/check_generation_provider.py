from .check_llm import Command as CheckLLMCommand


class Command(CheckLLMCommand):
    help = "Verify the configured local text-generation provider and model."
