import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile


# Patch external services
def patch_elasticsearch():
    """Patches Elasticsearch client to return mock responses"""
    mock_es = MagicMock()
    mock_es.indices.exists.return_value = True
    mock_es.indices.create.return_value = {"acknowledged": True}
    mock_es.index.return_value = {"_id": "test_id", "result": "created"}
    mock_es.search.return_value = {"hits": {"hits": [], "total": {"value": 0}}}
    mock_es.delete.return_value = {"result": "deleted"}

    return patch("elasticsearch.Elasticsearch", return_value=mock_es)


from files.hash_strategies import CompositeHashStrategy

# Now that Django is configured, we can import models
from files.models import File
from files.repository.file_repository import FileRepository
from files.services.file_service import FileService
from files.services.notification_service import CeleryNotificationService


# Common fixtures
@pytest.fixture
def sample_file():
    """Creates a SimpleUploadedFile for testing file uploads."""
    return SimpleUploadedFile(
        name="test_file.txt",
        content=b"This is a test file content.",
        content_type="text/plain",
    )


@pytest.fixture
def mock_file_manager():
    """Mocks the File.objects manager for database operations."""
    with patch("files.models.File.objects") as mock_manager:
        yield mock_manager


@pytest.fixture
def mock_index_file_task():
    """Creates a mock for the Celery index_file task with delay method."""
    mock_task = MagicMock()
    mock_task.delay = MagicMock()
    return mock_task


# Helper methods
def setup_mock_chain(mock_manager, return_value=None):
    """
    Sets up a complete mock chain for select_for_update().filter().first()

    Args:
        mock_manager: The mock manager to configure
        return_value: Value to be returned by first()

    Returns:
        Tuple of (mock_select_for_update, mock_filtered_qs)
    """
    mock_sfu = MagicMock()
    mock_filtered = MagicMock()
    mock_manager.select_for_update.return_value = mock_sfu
    mock_sfu.filter.return_value = mock_filtered
    mock_filtered.first.return_value = return_value
    return mock_sfu, mock_filtered


def assert_common_upload_checks(
    hash_strategy, file_obj, mock_sfu=None, mock_filtered_qs=None, secondary_hash=None
):
    """Common assertion checks for file uploads."""
    # Verify hash_strategy was called
    if hasattr(hash_strategy, "hash") and hasattr(
        hash_strategy.hash, "assert_called_once"
    ):
        hash_strategy.hash.assert_called_once()

    # Verify seek was called on file object
    if hasattr(file_obj, "mocked_seek") and hasattr(
        file_obj.mocked_seek, "assert_any_call"
    ):
        file_obj.mocked_seek.assert_any_call(0)

    # Verify select_for_update and filter were called if mocks provided
    # This is only for non-mock_mode repositories
    if (
        mock_sfu is not None
        and mock_filtered_qs is not None
        and secondary_hash is not None
    ):
        # Check if using repository with mock_mode (we won't check filter calls in that case)
        if not getattr(mock_sfu, "_mock_mode", False):
            mock_sfu.filter.assert_called_once_with(
                file_hash=secondary_hash, is_deleted=False
            )
            mock_filtered_qs.first.assert_called_once()


def setup_celery_task_mock(task_path="files.tasks.elastic.index_file"):
    """
    Sets up a mock for a Celery task with a delay method.
    Returns a context manager that yields the mock task.

    Usage:
        with setup_celery_task_mock() as mock_index_file:
            # Test code that would import and call index_file.delay
    """
    module_path, task_name = task_path.rsplit(".", 1)
    module_mock = MagicMock()
    task_mock = MagicMock()
    task_mock.delay = MagicMock()

    @contextmanager
    def _setup_mock():
        with patch.dict("sys.modules", {module_path: module_mock}):
            setattr(sys.modules[module_path], task_name, task_mock)
            yield task_mock

    return _setup_mock()
