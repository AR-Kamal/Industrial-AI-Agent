"""WSGI configuration for the AI Manufacturing chatbot."""

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "manufacturing_agent.settings.local")

application = get_wsgi_application()
