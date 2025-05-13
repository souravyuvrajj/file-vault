"""
Root conftest for Django tests—minimal necessary settings.
"""

import os
import django
import pytest
from django.conf import settings

# Point Django at our settings (will override below)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")


def pytest_configure():
    if not settings.configured:
        settings.configure(
            # ── In-memory DB ─────────────────────────────────────
            DATABASES={
                "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
            },
            # ── Installed apps ──────────────────────────────────
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "rest_framework",
                "files",  # your app under test
            ],
            # ── In-memory cache ────────────────────────────────
            CACHES={
                "default": {
                    "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                }
            },
            # ── Simplified REST framework ──────────────────────
            REST_FRAMEWORK={
                "DEFAULT_PERMISSION_CLASSES": [],
                "DEFAULT_AUTHENTICATION_CLASSES": [],
            },
            # ── File uploads ───────────────────────────────────
            MEDIA_ROOT=os.path.join(os.getcwd(), "test_media"),
            MEDIA_URL="/media/",
            ALLOWED_FILE_TYPES=["application/pdf", "text/plain", "image/jpeg"],
            # ── Other essentials ───────────────────────────────
            SECRET_KEY="test-secret-key",
            ROOT_URLCONF="core.urls",
        )
    django.setup()
