"""Local Windows development settings."""

from .base import *  # noqa: F403

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "var" / "db.sqlite3",  # noqa: F405
    }
}
