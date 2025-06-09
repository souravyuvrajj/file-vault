# files/tests/conftest.py

import os
import django
from django.conf import settings

# 1) Configure Django settings *before* any imports of DRF or models
if not settings.configured:
    settings.configure(
        INSTALLED_APPS=[
            "django.contrib.auth",
            "django.contrib.contenttypes",
            "rest_framework",
            "files",
        ],
        DATABASES={
            "default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}
        },
        # File upload limits
        FILE_UPLOAD_MAX_MEMORY_SIZE=524288000,
        MAX_FILENAME_LENGTH=255,
        ALLOWED_FILE_EXTENSIONS=["txt", "pdf", "jpg", "jpeg", "png", "mp4", "mp3"],
        DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
        # DRF minimal settings so APIClient can import
        REST_FRAMEWORK={"DEFAULT_PERMISSION_CLASSES": [], "DEFAULT_AUTHENTICATION_CLASSES": []},
        MEDIA_ROOT=os.path.join(os.getcwd(), "test_media"),
        MEDIA_URL="/media/",
        CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
        USE_TZ=True,
        TIME_ZONE="UTC",
    )
    django.setup()

settings.ROOT_URLCONF = "core.urls"

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from files.models import File  # safe now that apps are loaded


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def disable_throttling(monkeypatch):
    """Disables DRF throttling for tests that need to make many API requests.
    
    This fixture should only be used in API tests that need to bypass throttling.
    Not using autouse=True to avoid masking legitimate throttle-related errors.
    """
    monkeypatch.setattr("rest_framework.views.APIView.throttle_classes", [])
    monkeypatch.setattr("rest_framework.views.APIView.check_throttles", lambda self, request: None)


@pytest.fixture
def sample_file():
    return SimpleUploadedFile(name="hello.txt", content=b"hello world", content_type="text/plain")


@pytest.fixture
def oversized_file():
    max_size = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
    content = b"a" * (max_size + 1)
    return SimpleUploadedFile(name="big.bin", content=content, content_type="application/octet-stream")


@pytest.fixture
@pytest.mark.django_db
def persisted_file(tmp_path):
    # 1) create a file on disk
    disk = tmp_path / "persisted.txt"
    disk.write_bytes(b"persisted content")

    # 2) create DB record
    f = File.objects.create(
        original_filename="persisted.txt",
        file_type="txt",
        size=disk.stat().st_size,
        file_hash="0" * 64,  # mock sha256
        ref_count=1,
    )

    # 3) attach the physical file for download tests
    with open(disk, "rb") as fp:
        f.file.save("persisted.txt", fp, save=True)
    return f
