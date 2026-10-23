"""
Test-specific Django settings.

Uses SQLite for fast test execution without requiring PostgreSQL.
Import via: DJANGO_SETTINGS_MODULE=config.settings_test
"""

from .settings import *  # noqa: F401, F403

# Use SQLite for tests — no PostgreSQL dependency for unit tests
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# Disable throttling in tests
REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()  # noqa: F405
REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] = {}  # noqa: F405

# Faster password hashing for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Disable Celery in tests — run tasks synchronously
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True
