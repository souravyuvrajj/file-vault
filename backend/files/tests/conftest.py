"""
Test fixtures for files module tests.
"""

from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile

import tempfile
import uuid
from files.hash_strategies import CompositeHashStrategy

# Import concrete implementations and new interfaces
from files.interfaces import IFileRepository, IHashStrategy, INotificationService
from files.models import File
from files.repository.file_repository import FileRepository
from files.services.file_service import FileService
from files.services.notification_service import CeleryNotificationService
from files.tests.factories import FileFactory


# Configure test settings
@pytest.fixture(scope="session", autouse=True)
def configure_test_settings():
    """Configure settings for testing."""
    # Store original settings to restore later
    original_allowed_types = getattr(settings, "ALLOWED_FILE_TYPES", None)

    # Update settings for tests
    settings.ALLOWED_FILE_TYPES = [
        "text/plain",
        "application/pdf",
        "image/jpeg",
        "image/png",
    ]

    yield

    # Restore original settings
    if original_allowed_types is not None:
        settings.ALLOWED_FILE_TYPES = original_allowed_types


@pytest.fixture(autouse=True)
def disable_throttling():
    """Disable throttling for all tests"""
    with patch(
        "rest_framework.views.APIView.throttle_classes", []
    ) as throttle_classes_patch:
        with patch(
            "rest_framework.views.APIView.check_throttles"
        ) as throttle_check_patch:
            throttle_check_patch.return_value = None
            yield


@pytest.fixture
def mock_upload_use_case():
    """Create a mock UploadFileUseCase for views."""
    with patch("files.views.UploadFileUseCase") as MockUseCase:
        mock_use_case = MagicMock()
        MockUseCase.return_value = mock_use_case

        # Mock standard behaviors
        mock_file = MagicMock()
        mock_file.id = "test-file-id"
        mock_file.original_filename = "test_file.txt"
        mock_file.file_type = "text/plain"
        mock_file.uploaded_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_file.size = 100
        mock_file.ref_count = 1

        mock_use_case.execute.return_value = (
            mock_file,
            True,
        )  # Default return is a new file

        yield mock_use_case


@pytest.fixture
def sample_file():
    """Create a sample file for testing uploads."""
    return SimpleUploadedFile(
        name="test_file.txt",
        content=b"This is a test file content.",
        content_type="text/plain",
    )


@pytest.fixture
def oversized_file():
    """Create an oversized file for testing validation."""
    return SimpleUploadedFile(
        name="large_file.txt",
        content=b"This is a test file content, but we'll pretend it's very large.",
        content_type="text/plain",
    )


from files.hash_strategies import CompositeHashStrategy
from files.repository.file_repository import FileRepository
from files.services.notification_service import CeleryNotificationService


@pytest.fixture
def file_metadata():
    """Common file metadata used across tests."""
    return {
        "name": "test_file.txt",
        "type": "txt",
        "primary_hash": "test_primary_hash",
        "secondary_hash": "test_secondary_hash",
    }


@pytest.fixture
def file_content():
    """Sample file content for tests."""
    return b"This is a test file content."


@pytest.fixture
def mock_file_upload(file_content, file_metadata):
    """Creates a SimpleUploadedFile with mocked seek method."""
    uploaded_file = SimpleUploadedFile(
        name=file_metadata["name"], content=file_content, content_type="text/plain"
    )

    with patch.object(uploaded_file.file, "seek", return_value=None) as mocked_seek:
        uploaded_file.mocked_seek = mocked_seek
        yield uploaded_file


@pytest.fixture
def mock_hash_strategy(file_metadata):
    """Creates a mock hash strategy that returns predefined hashes."""
    strategy = MagicMock(spec=CompositeHashStrategy)
    strategy.hash.return_value = {
        "primary": file_metadata["primary_hash"],
        "secondary": file_metadata["secondary_hash"],
    }
    return strategy


@pytest.fixture
def file_service(mock_hash_strategy):
    """Creates a FileService instance with mocked dependencies."""
    mock_index_file = MagicMock()
    notification_service = CeleryNotificationService(index_file_func=mock_index_file)
    repository = FileRepository(mock_mode=True)  # Use mock mode to avoid DB access
    service = FileService(
        hash_strategy=mock_hash_strategy,
        notification_service=notification_service,
        repository=repository,
    )
    service.invalidate_caches = MagicMock()
    return service


@pytest.fixture(scope="session", autouse=True)
def configure_django_settings():
    """Ensure Django settings are configured before any tests run."""
    if not settings.configured:
        settings.configure(
            INSTALLED_APPS=[
                "django.contrib.auth",
                "django.contrib.contenttypes",
                "files",  # Ensure 'files' app is in INSTALLED_APPS
            ],
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            STORAGES={
                "default": {
                    "BACKEND": "django.core.files.storage.InMemoryStorage",
                }
            },
            CELERY_TASK_ALWAYS_EAGER=True,  # Run Celery tasks synchronously for tests
            CELERY_TASK_EAGER_PROPAGATES=True,
            USE_TZ=True,
            TIME_ZONE="UTC",
            # Add any other minimal settings required by your app or its dependencies
        )
        import django

        django.setup()


@pytest.fixture
def mock_file_upload():
    """Creates a mock file upload object for testing."""
    content = b"This is a test file content."
    file = SimpleUploadedFile(
        name="test_file.txt", content=content, content_type="text/plain"
    )
    # Mock the seek method to allow tracking its calls if needed by tests
    file.seek(0)
    file.mocked_seek = MagicMock(wraps=file.seek)  # wraps the original seek
    file.seek = file.mocked_seek
    return file


@pytest.fixture
def file_metadata(mock_file_upload):
    """Provides metadata for a mock file, including its hash."""
    # Use a real hash strategy to get a consistent hash for the mock file content
    strategy = CompositeHashStrategy()
    hashes = strategy.hash(mock_file_upload)
    mock_file_upload.seek(0)  # Reset seek after hashing

    return {
        "name": mock_file_upload.name,
        "type": "txt",  # Assuming txt for simplicity, adjust if needed
        "size": mock_file_upload.size,
        "primary_hash": hashes["primary"],
        "secondary_hash": hashes["secondary"],
    }


@pytest.fixture
def file_service() -> FileService:
    """Provides an instance of FileService with real dependencies for integration-style tests."""
    # Instantiate concrete implementations for the interfaces
    repository: IFileRepository = FileRepository()
    hash_strategy: IHashStrategy = CompositeHashStrategy()

    # For NotificationService, mock the Celery tasks it calls to avoid external dependencies
    # unless actual Celery integration is being tested.
    mock_index_task = MagicMock(name="mock_index_file_task")
    mock_update_task = MagicMock(name="mock_update_elasticsearch_document_task")

    notification_service: INotificationService = CeleryNotificationService(
        index_file_func=mock_index_task, update_file_func=mock_update_task
    )

    service = FileService(
        repository=repository,
        hash_strategy=hash_strategy,
        notification_service=notification_service,
    )
    return service


# Example of a fixture to create a persisted File object if needed for some tests
@pytest.fixture
@pytest.mark.django_db
def persisted_file(file_metadata):
    """Creates and persists a File object using FileFactory for testing."""
    # Create a unique file to avoid conflicts if multiple tests use this fixture
    unique_hash = f"{file_metadata['secondary_hash']}_{uuid.uuid4().hex[:6]}"
    file = FileFactory(
        original_filename=f"persisted_{file_metadata['name']}",
        file_type=file_metadata["type"],
        size=file_metadata["size"],
        file_hash=unique_hash,  # Use the unique hash
        ref_count=1,
    )
    # Simulate saving file content if necessary for the test scenario
    # For example, if the test involves accessing file.file.path or content:
    # content = b"persisted file content"
    # file.file.save(f"{unique_hash}.{file.file_type}", SimpleUploadedFile(name=file.original_filename, content=content))
    # file.save() # Ensure path is updated after save
    return file
