import logging
from unittest.mock import MagicMock, call, patch

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from files.models import File
from files.services import cache_service  # Import for direct patching
from files.services.file_service import FileService
from files.services.search_service import SearchService
from files.tests.factories import FileFactory

# Disable noisy logs during tests
logging.getLogger("files.file_service").setLevel(logging.ERROR)
logging.getLogger("files.search_service").setLevel(logging.ERROR)

# Test data
SAMPLE_FILE_ID = "test_file_id"


class TestCachingBehavior:
    """
    Tests for the caching behavior of both FileService and SearchService.

    These tests focus on:
    1. Cache hit behavior - verifying that cached data is returned and DB is not hit
    2. Cache invalidation - confirming cache keys are deleted after upload/delete operations
    """

    @pytest.fixture
    def file_service(self):
        """Create a FileService instance with mock hash strategy."""
        mock_hash_strategy = MagicMock()
        mock_hash_strategy.hash.return_value = {
            "primary": "test_primary_hash",
            "secondary": "test_secondary_hash",
        }
        # Add mock repository and notification_service
        mock_repository = MagicMock()
        mock_notification_service = MagicMock()
        return FileService(
            repository=mock_repository,
            hash_strategy=mock_hash_strategy,
            notification_service=mock_notification_service,
        )

    @pytest.fixture
    def search_service(self):
        """Create a SearchService instance."""
        return SearchService(cache_timeout=300)

    @pytest.fixture
    def mock_file(self):
        """Create a mock file for testing using FileFactory."""
        # Use FileFactory to build a mock file instance without saving to DB
        # This is suitable for tests that mock DB interactions or don't need persistence
        # For tests requiring DB state, use FileFactory.create()
        # return FileFactory.build(
        return FileFactory.create(
            size=1024,
            file_hash="test_hash_123",
            original_filename="test_file.txt",
            file_type="txt",
            ref_count=2,
        )

    @pytest.fixture
    def mock_file_obj(self):
        """Create a mock file object."""
        file_content = b"Test content for file"
        file_obj = SimpleUploadedFile(
            name="test_file.txt", content=file_content, content_type="text/plain"
        )
        return file_obj

    @pytest.fixture
    def search_result(self):
        """Create a mock search result."""
        return {
            "status": "success",
            "results": [{"id": "file1", "name": "document.pdf"}],
            "total": 1,
            "page": 1,
            "page_size": 10,
            "fallback": True,
        }

    def test_storage_summary_cache_hit(self, file_service):
        """
        Test that the storage summary is served from cache when available.
        """
        # Arrange
        cache_key = "storage_summary"
        cached_summary = {
            "total_file_size": 10000,
            "deduplicated_storage": 5000,
            "storage_saved": 5000,
            "savings_percentage": 50.0,
        }

        # Pre-seed the cache with our data
        with patch(
            "files.services.cache_service.get_data", return_value=cached_summary
        ) as mock_get_data, patch(
            "files.services.cache_service.set_data"
        ) as mock_set_data:

            # Act
            result = file_service.get_storage_summary(use_cache=True)

            # Assert
            assert result == cached_summary
            mock_get_data.assert_called_once_with(cache_key)
            mock_set_data.assert_not_called()

    def test_search_cache_hit(self, search_service):
        """
        Test that search results are served from cache when available.
        """
        # Arrange
        search_params = {"search_term": "document", "page": 1, "page_size": 10}
        cache_key = "search:search_term=document&page=1&page_size=10"
        cached_results = {
            "status": "success",
            "results": [{"id": "file1", "name": "document.pdf"}],
            "total": 1,
            "page": 1,
            "page_size": 10,
            "fallback": True,
        }

        # Set up mocks
        with patch(
            "files.services.cache_service.get_data", return_value=cached_results
        ) as mock_get_data, patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate, patch.object(
            search_service, "_search_db"
        ) as mock_db_search, patch.object(
            search_service, "_search_es"
        ) as mock_es_search:

            # Mock validate_search_params to return processed params
            mock_validate.return_value = {
                "search_term": "document",
                "file_type": None,
                "min_size": None,
                "max_size": None,
                "start_date": None,
                "end_date": None,
                "page": 1,
                "page_size": 10,
            }

            # Act
            result = search_service.search_files(search_params)

            # Assert
            assert result == cached_results
            mock_get_data.assert_called_once()  # Verify cache_service.get_data was checked
            mock_db_search.assert_not_called()
            mock_es_search.assert_not_called()

    @pytest.mark.django_db
    def test_cache_invalidation_after_upload(self, file_service, mock_file_obj):
        """
        Test that caches are invalidated after file upload via upload_file method.
        """
        with patch(
            "files.services.cache_service.invalidate_storage_summary_cache"
        ) as mock_invalidate_summary, patch(
            "files.services.cache_service.invalidate_all_search_caches"
        ) as mock_invalidate_search:
            # Create a mock file with content to match the size
            mock_content = b"x" * 1024  # 1024 bytes
            mock_file_obj = SimpleUploadedFile(
                "test_file.txt", mock_content, content_type="text/plain"
            )

            # Also patch the hash strategy to return a fixed hash
            with patch.object(file_service.hash_strategy, "hash") as mock_hash:
                mock_hash.return_value = {
                    "primary": "test_primary_hash",
                    "secondary": "test_hash_123",
                }

                # Patch find_by_hash to return None (no duplicate found)
                with patch.object(
                    file_service.repository, "find_by_hash", return_value=None
                ) as mock_find_hash:
                    # Patch the save method on the repository to return a mock file and True (created)
                    mock_new_file = FileFactory.build(
                        size=1024,
                        file_hash="test_hash_123",
                        original_filename="test_file.txt",
                        file_type="txt",
                        ref_count=1,
                    )

                    with patch.object(
                        file_service.repository,
                        "save",
                        return_value=(mock_new_file, True),
                    ) as mock_save:
                        # Mock notification service to avoid real calls
                        with patch.object(
                            file_service.notification_service, "notify_index"
                        ) as mock_notify:

                            # Act - Call upload_file instead of deduplicate
                            file_service.upload_file(
                                mock_file_obj, "test_file.txt", "txt"
                            )

                            # Assert cache invalidation was called
                            mock_invalidate_summary.assert_called_once()
                            mock_invalidate_search.assert_called_once()
                            # Verify other methods were called appropriately
                            mock_hash.assert_called_once()
                            mock_find_hash.assert_called_once()
                            mock_save.assert_called_once()
                            mock_notify.assert_called_once()

    @pytest.mark.django_db
    def test_cache_invalidation_after_delete(self, file_service, mock_file):
        """
        Test that caches are invalidated after file deletion.
        """
        with patch(
            "files.services.cache_service.invalidate_storage_summary_cache"
        ) as mock_invalidate_summary, patch(
            "files.services.cache_service.invalidate_all_search_caches"
        ) as mock_invalidate_search, patch.object(
            file_service.repository, "get_by_id", return_value=mock_file
        ) as mock_get_by_id, patch.object(
            file_service.repository, "mark_deleted"
        ) as mock_mark_deleted, patch.object(
            mock_file, "decrement_ref_count"
        ) as mock_decrement_ref:  # If mock_file is a MagicMock

            # Scenario 1: ref_count > 1 (decrement)
            mock_file.ref_count = 2  # Setup for decrement path
            file_service.delete_file(str(mock_file.id))
            mock_invalidate_summary.assert_called_once()
            mock_invalidate_search.assert_called_once()
            mock_decrement_ref.assert_called_once()
            mock_mark_deleted.assert_not_called()  # Ensure mark_deleted wasn't called

            # Reset mocks for next scenario
            mock_invalidate_summary.reset_mock()
            mock_invalidate_search.reset_mock()
            mock_decrement_ref.reset_mock()
            mock_mark_deleted.reset_mock()

            # Scenario 2: ref_count == 1 (mark deleted)
            mock_file.ref_count = 1  # Setup for mark_deleted path
            file_service.delete_file(str(mock_file.id))
            mock_invalidate_summary.assert_called_once()
            mock_invalidate_search.assert_called_once()
            mock_mark_deleted.assert_called_once()
            mock_decrement_ref.assert_not_called()  # Ensure decrement wasn't called

    def test_cache_miss_stores_result(self, search_service, search_result):
        """
        Test that search results can be retrieved either from cache or from a database search.
        """
        # Arrange - Create a test case for a search
        search_params = {"search_term": "document"}

        # Test setup with simplified mocking approach
        with patch.object(search_service, "_search_db") as mock_db_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ) as mock_cache_get, patch(
            "files.services.cache_service.set_data"
        ) as mock_cache_set, patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate:

            # Configure validator mock to return processed params
            mock_validate.return_value = {
                "search_term": "document",
                "file_type": None,
                "min_size": None,
                "max_size": None,
                "start_date": None,
                "end_date": None,
                "page": 1,
                "page_size": 10,
            }

            # Setup mock to return search result
            mock_db_search.return_value = search_result

            # Set USE_ELASTICSEARCH to False to ensure we use the database search
            with patch("django.conf.settings") as mock_settings:
                mock_settings.USE_ELASTICSEARCH = False

                # Act
                result = search_service.search_files(search_params)

                # Assert
                # Should have called the database search method
                mock_db_search.assert_called_once()

                # Should match our mock search result
                assert result == search_result
                # Assert cache_service methods were called
                mock_cache_get.assert_called_once()
                mock_cache_set.assert_called_once()

    # Remove test_invalidate_caches_method and test_invalidate_caches_without_pattern_support
    # as their functionality is now covered by testing cache_service directly (if needed)
    # or implicitly by the invalidation calls in other tests.
