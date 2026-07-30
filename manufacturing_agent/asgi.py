"""ASGI configuration for the AI Manufacturing chatbot."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "manufacturing_agent.settings.local")

application = get_asgi_application()
