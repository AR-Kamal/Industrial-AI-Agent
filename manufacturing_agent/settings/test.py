"""Fast, isolated settings for automated tests."""

import os

os.environ.setdefault("SECRET_KEY", "test-only-secret-key-not-for-runtime")

from .base import *  # noqa: E402,F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

LLM_PROVIDER = "ollama"
LLM_BASE_URL = "http://127.0.0.1:11434/v1"
LLM_API_KEY = "test-placeholder"
LLM_TEXT_MODEL = "test-model"
LLM_TIMEOUT_SECONDS = 1.0
LLM_TEMPERATURE = 0.0
LLM_MAX_TOKENS = 128
GEMINI_API_KEY = ""

INGESTION_TARGET_CHUNK_TOKENS = 400
INGESTION_CHUNK_OVERLAP_TOKENS = 50
INGESTION_MIN_CHUNK_TOKENS = 20
INGESTION_MAX_CHUNK_TOKENS = 500
KNOWLEDGE_MAX_UPLOAD_BYTES = 2_000_000
