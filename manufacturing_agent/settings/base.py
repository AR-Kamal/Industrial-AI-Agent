"""Shared Django settings."""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env(
    DEBUG=(bool, False),
    SECRET_KEY=(str, ""),
    ALLOWED_HOSTS=(list, ["127.0.0.1", "localhost"]),
    LOG_LEVEL=(str, "INFO"),
    LLM_PROVIDER=(str, "ollama"),
    LLM_BASE_URL=(str, "http://127.0.0.1:11434/v1"),
    LLM_API_KEY=(str, "ollama"),
    LLM_TEXT_MODEL=(str, "gemma3:4b"),
    LLM_TIMEOUT_SECONDS=(float, 60.0),
    LLM_TEMPERATURE=(float, 0.1),
    LLM_MAX_TOKENS=(int, 800),
    INGESTION_TARGET_CHUNK_TOKENS=(int, 600),
    INGESTION_CHUNK_OVERLAP_TOKENS=(int, 75),
    INGESTION_MIN_CHUNK_TOKENS=(int, 100),
    INGESTION_MAX_CHUNK_TOKENS=(int, 900),
    KNOWLEDGE_MAX_UPLOAD_BYTES=(int, 52_428_800),
    EMBEDDING_PROVIDER=(str, "ollama"),
    EMBEDDING_BASE_URL=(str, "http://127.0.0.1:11434"),
    EMBEDDING_MODEL=(str, ""),
    EMBEDDING_TIMEOUT_SECONDS=(float, 120.0),
    EMBEDDING_BATCH_SIZE=(int, 16),
    VECTOR_STORE_PROVIDER=(str, "qdrant"),
    QDRANT_MODE=(str, "local"),
    QDRANT_PATH=(str, "var/vector_store"),
    VECTOR_DISTANCE_METRIC=(str, "cosine"),
    RETRIEVAL_DEFAULT_TOP_K=(int, 5),
    RETRIEVAL_MAX_TOP_K=(int, 10),
    RETRIEVAL_MIN_SCORE=(str, ""),
    SAFETY_RETRIEVAL_ENABLED=(bool, True),
    SAFETY_RETRIEVAL_TOP_K=(int, 3),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY must be set in .env or the environment.")

DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

LLM_PROVIDER = env("LLM_PROVIDER")
LLM_BASE_URL = env("LLM_BASE_URL")
LLM_API_KEY = env("LLM_API_KEY")
LLM_TEXT_MODEL = env("LLM_TEXT_MODEL")
LLM_TIMEOUT_SECONDS = env("LLM_TIMEOUT_SECONDS")
LLM_TEMPERATURE = env("LLM_TEMPERATURE")
LLM_MAX_TOKENS = env("LLM_MAX_TOKENS")
INGESTION_TARGET_CHUNK_TOKENS = env("INGESTION_TARGET_CHUNK_TOKENS")
INGESTION_CHUNK_OVERLAP_TOKENS = env("INGESTION_CHUNK_OVERLAP_TOKENS")
INGESTION_MIN_CHUNK_TOKENS = env("INGESTION_MIN_CHUNK_TOKENS")
INGESTION_MAX_CHUNK_TOKENS = env("INGESTION_MAX_CHUNK_TOKENS")
KNOWLEDGE_MAX_UPLOAD_BYTES = env("KNOWLEDGE_MAX_UPLOAD_BYTES")
EMBEDDING_PROVIDER = env("EMBEDDING_PROVIDER")
EMBEDDING_BASE_URL = env("EMBEDDING_BASE_URL")
EMBEDDING_MODEL = env("EMBEDDING_MODEL")
EMBEDDING_TIMEOUT_SECONDS = env("EMBEDDING_TIMEOUT_SECONDS")
EMBEDDING_BATCH_SIZE = env("EMBEDDING_BATCH_SIZE")
VECTOR_STORE_PROVIDER = env("VECTOR_STORE_PROVIDER")
QDRANT_MODE = env("QDRANT_MODE")
QDRANT_PATH = env("QDRANT_PATH")
VECTOR_DISTANCE_METRIC = env("VECTOR_DISTANCE_METRIC")
RETRIEVAL_DEFAULT_TOP_K = env("RETRIEVAL_DEFAULT_TOP_K")
RETRIEVAL_MAX_TOP_K = env("RETRIEVAL_MAX_TOP_K")
_retrieval_min_score = env("RETRIEVAL_MIN_SCORE")
RETRIEVAL_MIN_SCORE = (
    float(_retrieval_min_score) if _retrieval_min_score.strip() else None
)
SAFETY_RETRIEVAL_ENABLED = env("SAFETY_RETRIEVAL_ENABLED")
SAFETY_RETRIEVAL_TOP_K = env("SAFETY_RETRIEVAL_TOP_K")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.accounts",
    "apps.chatbot",
    "apps.knowledge_base",
    "apps.feedback",
    "apps.ai_gateway",
    "apps.safety",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "manufacturing_agent.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    }
]

WSGI_APPLICATION = "manufacturing_agent.wsgi.application"
ASGI_APPLICATION = "manufacturing_agent.asgi.application"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": (
            "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
        )
    },
    {"NAME": ("django.contrib.auth.password_validation.MinimumLengthValidator")},
    {"NAME": ("django.contrib.auth.password_validation.CommonPasswordValidator")},
    {"NAME": ("django.contrib.auth.password_validation.NumericPasswordValidator")},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Singapore"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "var" / "static"
MEDIA_ROOT = BASE_DIR / "var" / "documents"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "chatbot:index"
LOGOUT_REDIRECT_URL = "home"

SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

LOG_LEVEL = env("LOG_LEVEL").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "structured": {
            "()": "manufacturing_agent.logging.JsonFormatter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "structured",
        }
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django.server": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "httpx": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
}
