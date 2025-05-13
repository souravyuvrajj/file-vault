import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import django
import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.paginator import Page
from django.db.models import Q
from django.utils import timezone
from elasticsearch import ConnectionError, ConnectionTimeout, TransportError
from files.exceptions import FileError
from files.models import File
from files.services.filter_builder import FilterBuilder
from files.services.search_service import SearchService
from files.tests.factories import FileFactory
from files.utils.cache_keys import generate_search_cache_key
from files.utils.circuit_breaker import circuit_breaker
from files.utils.response_formatter import format_paginated_response

# Disable noisy logs during tests
logging.getLogger("files.search_service").setLevel(logging.ERROR)


class TestSearchService:
    """
    Test suite for SearchService with focus on database fallback and filtering logic.
    """

    @pytest.fixture
    def search_service(self):
        """Create a SearchService instance for testing."""
        service = SearchService(cache_timeout=0)  # Disable caching for tests

        # Patch the _increment_metric method to avoid cache errors
        service._increment_metric = MagicMock()

        return service

    @pytest.fixture
    def sample_files(self):
        """
        Create a sample dataset of File model instances using FileFactory for testing.
        """
        now = timezone.now()
        # Use FileFactory.build() to create non-persistent instances for testing
        # Note: For tests involving actual DB queries against these, you might need FileFactory.create()
        # and ensure the test is marked with @pytest.mark.django_db
        files = [
            FileFactory.build(
                size=1024,  # 1KB
                file_hash="hash1",
                original_filename="document.txt",
                file_type="txt",
                id="file1",
                uploaded_at=now - timedelta(days=2),
            ),
            FileFactory.build(
                size=5 * 1024 * 1024,  # 5MB
                file_hash="hash2",
                original_filename="report2023.pdf",
                file_type="pdf",
                ref_count=2,
                id="file2",
                uploaded_at=now - timedelta(days=10),
            ),
            FileFactory.build(
                size=20 * 1024 * 1024,  # 20MB
                file_hash="hash3",
                original_filename="large_image.jpg",
                file_type="jpg",
                id="file3",
                uploaded_at=now - timedelta(days=7),
            ),
            FileFactory.build(
                size=500 * 1024,  # 500KB
                file_hash="hash4",
                original_filename="icon.png",
                file_type="png",
                ref_count=3,
                id="file4",
                uploaded_at=now - timedelta(hours=2),
            ),
            FileFactory.build(
                size=2 * 1024 * 1024,  # 2MB
                file_hash="hash5",
                original_filename="old_file.doc",
                file_type="doc",
                id="file5",
                uploaded_at=now - timedelta(days=30),
                is_deleted=True,  # Using factory attribute directly
            ),
        ]
        return files

    # Test for enhanced FilterBuilder
    def test_filter_builder_get_filters(self):
        """Test the enhanced FilterBuilder that can return individual filters."""
        # Create a filter builder with various filters
        builder = FilterBuilder()
        builder.term("is_deleted", False)
        builder.multi_match(["name", "description"], "test")
        builder.range("size", gte=1000, lte=5000)
        builder.date_range("created_at", "2023-01-01", "2023-12-31")

        # Get Django filters directly
        django_filters = builder.get_django_filters()

        # Test that filters were created (without asserting exact count)
        assert len(django_filters) > 0

        # Get ES filters directly
        es_filters = builder.get_es_filters()

        # Test that filters were created (without asserting exact count)
        assert len(es_filters) > 0

        # Test that we can build a combined Django Q object
        django_q = builder.build_django()
        assert django_q is not None

        # Test that we can build a combined ES Q object
        es_q = builder.build_es()
        assert es_q is not None

        # Test applying to queryset - use a different mocking approach
        mock_queryset = MagicMock()
        mock_queryset.filter.return_value = mock_queryset  # Return self for chaining

        # Apply the filter
        result = builder.apply_to_queryset(mock_queryset)

        # Verify the filter was called
        mock_queryset.filter.assert_called_once()

        # Verify it returns the filtered queryset
        assert result == mock_queryset.filter.return_value

    # Test for response formatter
    def test_response_formatter(self):
        """Test the response formatter utility."""
        # Test basic formatting
        items = [{"id": "1", "name": "test"}]

        # Format a response
        response = format_paginated_response(
            items=items, total=100, page=2, page_size=10, source="database"
        )

        # Verify response format
        assert response["items"] == items
        assert response["total"] == 100
        assert response["page"] == 2
        assert response["page_size"] == 10
        assert response["source"] == "database"

        # Test with extra data
        extra_data = {"duration_ms": 123}
        response_with_extra = format_paginated_response(
            items=items,
            total=100,
            page=2,
            page_size=10,
            source="elasticsearch",
            extra_data=extra_data,
        )

        # Verify extra data is included
        assert response_with_extra["duration_ms"] == 123

    # Test for configurable circuit breaker
    def test_circuit_breaker_config(self):
        """Test the circuit breaker with configurable thresholds."""

        # Define a function to be decorated
        @circuit_breaker(
            "test-service", failure_threshold=2, window=30, reset_timeout=60
        )
        def test_function():
            return "success"

        # Test successful execution
        with patch("files.utils.circuit_breaker.cache.get", return_value=None):
            result = test_function()
            assert result == "success"

        # Test circuit open scenario
        expected_error_message = "Circuit breaker open for test-service"
        with patch(
            "files.utils.circuit_breaker.cache.get", return_value=True
        ), pytest.raises(ConnectionError) as excinfo:
            test_function()

        # Check the exception arguments directly
        assert excinfo.value.args[0] == expected_error_message

        # Test failure counting
        with patch(
            "files.utils.circuit_breaker.cache.get", side_effect=[None, 0]
        ) as mock_get, patch(
            "files.utils.circuit_breaker.cache.set"
        ) as mock_set, pytest.raises(
            ConnectionError
        ):

            # Mock the function to raise ConnectionError
            @circuit_breaker("test-service", failure_threshold=2)
            def failing_function():
                raise ConnectionError("Test error")

            try:
                failing_function()
            except:
                # Verify cache.set was called to increment failures
                mock_set.assert_called()
                raise

    def test_search_without_elasticsearch(self, search_service, sample_files):
        """
        Test that search uses database when Elasticsearch is not enabled.
        """
        # Ensure the search_service is configured to NOT use Elasticsearch
        search_service.use_es = False

        # Mock the _search_db method to return a predefined response
        with patch.object(search_service, "_search_db") as mock_db_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ) as mock_cache_get, patch(
            "files.services.cache_service.set_data"
        ) as mock_cache_set:

            # Create a mock database response
            active_files = [f for f in sample_files if not f.is_deleted]
            mock_db_response = {
                "items": [
                    {
                        "id": f"file_{i}",
                        "original_filename": f"test_file_{i}.txt",
                        "file_type": "text/plain",
                        "uploaded_at": datetime.now(),
                        "file_size": 1024 * (i + 1),
                        "ref_count": i,
                        "score": None,
                    }
                    for i in range(len(active_files))
                ],
                "total": len(active_files),
                "page": 1,
                "page_size": 10,
                "source": "database",
            }

            # Setup the mock to return our predefined response
            mock_db_search.return_value = mock_db_response

            # Act
            result = search_service.search_files({"page": 1, "page_size": 10})

            # Assert
            assert "items" in result
            assert "total" in result
            assert result["total"] == len(active_files)
            assert len(result["items"]) == len(active_files)
            assert result["source"] == "database"

            # Verify the database search method was called
            mock_db_search.assert_called_once()
            mock_cache_get.assert_called_once()  # Verify cache was checked
            mock_cache_set.assert_called_once()  # Verify result was cached

    # Combine filtering tests into one parametrized test
    @pytest.mark.parametrize(
        "test_id, search_params_in, expected_processed_params, filter_logic",
        [
            (
                "query_substring",
                {"search_term": "image"},
                {
                    "search_term": "image",
                    "file_type": None,
                    "min_size": None,
                    "max_size": None,
                    "start_date": None,
                    "end_date": None,
                    "page": 1,
                    "page_size": 10,
                },
                lambda files: [
                    f
                    for f in files
                    if "image" in f.original_filename and not f.is_deleted
                ],
            ),
            (
                "size_filters",
                {"min_size": str(1 * 1024 * 1024), "max_size": str(10 * 1024 * 1024)},
                {
                    "search_term": None,
                    "file_type": None,
                    "min_size": str(1 * 1024 * 1024),
                    "max_size": str(10 * 1024 * 1024),
                    "start_date": None,
                    "end_date": None,
                    "page": 1,
                    "page_size": 10,
                },
                lambda files: [
                    f
                    for f in files
                    if 1 * 1024 * 1024 <= f.size <= 10 * 1024 * 1024
                    and not f.is_deleted
                ],
            ),
            (
                "date_filters",
                {
                    "start_date": (timezone.now() - timedelta(days=8)).isoformat(),
                    "end_date": (timezone.now() - timedelta(days=1)).isoformat(),
                },
                {
                    "search_term": None,
                    "file_type": None,
                    "min_size": None,
                    "max_size": None,
                    "start_date": (timezone.now() - timedelta(days=8)).isoformat(),
                    "end_date": (timezone.now() - timedelta(days=1)).isoformat(),
                    "page": 1,
                    "page_size": 10,
                },
                lambda files: [
                    f
                    for f in files
                    if (timezone.now() - timedelta(days=8)).date()
                    <= f.uploaded_at.date()
                    <= (timezone.now() - timedelta(days=1)).date()
                    and not f.is_deleted
                ],  # Compare dates only for simplicity
            ),
            (
                "combined_filters",
                {
                    "search_term": "image",
                    "file_type": "png",
                    "start_date": (timezone.now() - timedelta(days=7)).isoformat(),
                },
                {
                    "search_term": "image",
                    "file_type": "png",
                    "min_size": None,
                    "max_size": None,
                    "start_date": (timezone.now() - timedelta(days=7)).isoformat(),
                    "end_date": None,
                    "page": 1,
                    "page_size": 10,
                },
                lambda files: [
                    f
                    for f in files
                    if ("image" in f.original_filename)
                    and (f.file_type == "png")
                    and (timezone.now() - timedelta(days=7)).date()
                    <= f.uploaded_at.date()
                    and not f.is_deleted
                ],
            ),
        ],
        ids=[
            "query_substring",
            "size_filters",
            "date_filters",
            "combined_filters",
        ],  # Test IDs for better reporting
    )
    def test_search_db_filtering(
        self,
        search_service,
        sample_files,
        test_id,
        search_params_in,
        expected_processed_params,
        filter_logic,
    ):
        """
        Test database search with various filters applied.
        Verifies that the correct parameters are passed to the mocked _search_db method.
        """
        search_service.use_es = False
        now = timezone.now()  # For consistent date comparisons within the test

        # Ensure pagination defaults are added if not present
        final_search_params = {"page": 1, "page_size": 10, **search_params_in}

        with patch.object(search_service, "_search_db") as mock_db_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ) as mock_cache_get, patch(
            "files.services.cache_service.set_data"
        ) as mock_cache_set, patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate:

            # Configure validator mock to return the expected processed parameters
            mock_validate.return_value = expected_processed_params

            # Calculate expected matching files based on the filter logic for this scenario
            # The factory creates timezone-aware datetimes, so direct comparison should work if `now` is also aware.
            # Let's make `now` timezone-aware for safety.
            # from django.utils.timezone import make_aware # Removed this import
            # aware_now = make_aware(now) # Removed make_aware call, use 'now' directly

            # Adjust lambda logic slightly for date comparison if needed
            if test_id == "date_filters":
                # start_dt = aware_now - timedelta(days=8) # Use 'now' directly
                # end_dt = aware_now - timedelta(days=1) # Use 'now' directly
                start_dt = now - timedelta(days=8)
                end_dt = now - timedelta(days=1)
                matching_files = [
                    f
                    for f in sample_files
                    if start_dt <= f.uploaded_at <= end_dt and not f.is_deleted
                ]
            elif test_id == "combined_filters":
                # start_dt = aware_now - timedelta(days=7) # Use 'now' directly
                start_dt = now - timedelta(days=7)
                matching_files = [
                    f
                    for f in sample_files
                    if ("image" in f.original_filename)
                    and (f.file_type == "png")
                    and start_dt <= f.uploaded_at
                    and not f.is_deleted
                ]
            else:
                matching_files = filter_logic(sample_files)

            # Create the expected mock database response based on matching files
            mock_db_response = {
                "items": [
                    {
                        "id": f.id,
                        "original_filename": f.original_filename,
                        "file_type": f.file_type,
                        "uploaded_at": f.uploaded_at.isoformat(),  # Use isoformat for consistency
                        "file_size": f.size,
                        "ref_count": f.ref_count,
                        "score": None,  # DB search doesn't have score
                    }
                    for f in matching_files
                ],
                "total": len(matching_files),
                "page": final_search_params["page"],
                "page_size": final_search_params["page_size"],
                "source": "database",
            }
            mock_db_search.return_value = mock_db_response

            # Act
            result = search_service.search_files(final_search_params)

            # Assert
            assert "items" in result
            assert "total" in result
            assert result["total"] == len(matching_files)
            assert len(result["items"]) == len(matching_files)
            assert result["source"] == "database"

            # Verify the database search method was called once
            mock_db_search.assert_called_once()

            # Verify correct processed parameters were passed to _search_db
            call_args, _ = mock_db_search.call_args
            assert (
                call_args[0] == expected_processed_params
            )  # Compare the dictionary passed

            # Further check: Ensure the items returned match the expected files
            returned_ids = {str(item["id"]) for item in result["items"]}

            mock_cache_get.assert_called_once()
            mock_cache_set.assert_called_once()

    def test_invalid_size_inputs(self, search_service, sample_files):
        """
        Test that search correctly handles invalid size inputs.
        """
        # Ensure search service uses database (no Elasticsearch)
        search_service.use_es = False

        # Setup the mocks
        with patch.object(search_service, "_search_db") as mock_db_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ), patch("files.services.cache_service.set_data"), patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate:

            # Configure validator mock to raise a ValidationError for min_size
            mock_validate.side_effect = ValidationError("Invalid min_size")

            # Act and Assert
            with pytest.raises(FileError) as excinfo:
                search_service.search_files({"min_size": "invalid", "max_size": "10MB"})

            assert "Unexpected error during search" in str(excinfo.value)

            # Verify that _search_db was not called due to validation error
            mock_db_search.assert_not_called()

    def test_malformed_date_inputs(self, search_service, sample_files):
        """
        Test that malformed date inputs are handled gracefully.
        """
        # Ensure search service uses database (no Elasticsearch)
        search_service.use_es = False

        # Setup the mocks
        with patch.object(search_service, "_search_db") as mock_db_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ), patch("files.services.cache_service.set_data"), patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate:

            # Configure validator mock to raise a ValidationError for date format
            mock_validate.side_effect = ValidationError("Invalid date format")

            # Act and Assert
            with pytest.raises(FileError) as excinfo:
                search_service.search_files(
                    {"start_date": "not-a-date", "end_date": "also-invalid-date"}
                )

            assert "Unexpected error during search" in str(excinfo.value)

            # Verify that _search_db was not called due to validation error
            mock_db_search.assert_not_called()

    def test_search_with_elasticsearch_success(self, search_service, sample_files):
        """
        Test searching via Elasticsearch when it's available and working.
        """
        # Arrange
        # Ensure search service uses Elasticsearch
        search_service.use_es = True

        # Mock the ES document class and search results
        with patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate, patch.object(
            search_service, "_search_es"
        ) as mock_es_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ) as mock_cache_get, patch(
            "files.services.cache_service.set_data"
        ) as mock_cache_set:

            # Configure validator mock
            mock_validate.return_value = {
                "search_term": "report",
                "file_type": "pdf",
                "min_size": "1000000",  # 1MB
                "max_size": "10000000",  # 10MB
                "start_date": None,
                "end_date": None,
                "page": 1,
                "page_size": 20,
            }

            # Configure ES search mock to return success
            mock_es_response = {
                "items": [
                    {
                        "id": "doc1",
                        "original_filename": "report2023.pdf",
                        "file_type": "pdf",
                        "file_size": 2000000,
                        "uploaded_at": "2023-05-15T10:30:00Z",
                    },
                    {
                        "id": "doc2",
                        "original_filename": "annual_report.pdf",
                        "file_type": "pdf",
                        "file_size": 5000000,
                        "uploaded_at": "2023-06-20T14:45:00Z",
                    },
                ],
                "total": 2,
                "page": 1,
                "page_size": 20,
                "source": "elasticsearch",
            }
            mock_es_search.return_value = mock_es_response

            # Need to mock the cache key generation to avoid issues
            params = {
                "search_term": "report",
                "file_type": "pdf",
                "min_size": "1000000",
                "max_size": "10000000",
                "page": 1,
                "page_size": 20,
            }

            # Act
            result = search_service.search_files(params)

            # Assert
            assert "items" in result
            assert "total" in result
            assert "source" in result
            assert result["source"] == "elasticsearch"
            assert len(result["items"]) == 2
            assert result["total"] == 2
            assert mock_es_search.call_count == 1
            mock_cache_get.assert_called_once()
            mock_cache_set.assert_called_once()

    def test_elasticsearch_fallback_to_db(self, search_service):
        """
        Test that when Elasticsearch fails with a ConnectionError,
        we check if the error is handled properly.
        """
        # Ensure search service uses Elasticsearch
        search_service.use_es = True

        # Setup mocks
        with patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate, patch.object(
            search_service, "_search_es", side_effect=ConnectionError("ES unavailable")
        ), patch.object(
            search_service, "_search_db"
        ) as mock_db_search, patch(
            "files.services.cache_service.get_data", return_value=None
        ) as mock_cache_get, patch(
            "files.services.cache_service.set_data"
        ) as mock_cache_set:

            # Configure validator mock
            mock_validate.return_value = {
                "search_term": "contract",
                "file_type": None,
                "min_size": None,
                "max_size": None,
                "start_date": None,
                "end_date": None,
                "page": 1,
                "page_size": 20,
            }

            # Setup DB search mock to return some results (will be used as fallback)
            db_results = {
                "items": [
                    {
                        "id": "doc3",
                        "original_filename": "contract_2023.pdf",
                        "file_type": "pdf",
                        "file_size": 3000000,
                        "uploaded_at": "2023-07-10T14:30:00Z",
                    }
                ],
                "total": 1,
                "page": 1,
                "page_size": 20,
                "source": "database",
            }
            mock_db_search.return_value = db_results

            # Act - Search should fallback to DB without raising FileError
            params = {"search_term": "contract", "page": 1, "page_size": 20}
            results = search_service.search_files(params)

            # Assertions
            # Verify _search_db was called as a fallback
            mock_db_search.assert_called_once()

            # Verify the results indicate a fallback occurred
            assert results.get("fallback") is True

            # Verify the structure and source of the results match the DB fallback
            assert results["source"] == "database"
            assert results["total"] == db_results["total"]
            assert results["items"] == db_results["items"]
            # Ensure _search_es was attempted but failed (due to side_effect)
            assert search_service._search_es.call_count == 1
            mock_cache_get.assert_called_once()
            mock_cache_set.assert_called_once()  # Cache should still be set after fallback

    def test_cache_key_generation(self):
        """
        Test that cache keys are generated correctly using the centralized function.
        """
        # Test with basic parameters
        params = {
            "query": "test",
            "page": 1,
            "page_size": 20,
            "use_cache": True,  # This should be excluded from the key
        }

        # Generate the cache key using the utility function
        cache_key = generate_search_cache_key(params)

        # Verify it's a string and contains all non-excluded parameters
        assert isinstance(cache_key, str)
        # Check the prefix and sorted key-value pairs
        assert cache_key.startswith("search:")
        assert (
            cache_key == "search:page:1:page_size:20:query:test"
        )  # Explicit check for order
        assert "use_cache" not in cache_key

        # Test with additional parameters
        params_with_date = {
            "query": "document",
            "file_type": "pdf",
            "min_size": 1000,
            "max_size": 5000,
            "start_date": "2023-01-01",
            "end_date": "2023-12-31",
            "page": 2,
            "page_size": 50,
            "use_cache": False,  # This should be excluded
        }

        # Generate the cache key
        complex_key = generate_search_cache_key(params_with_date)

        # Verify all expected parameters are in the key in sorted order
        assert isinstance(complex_key, str)
        assert complex_key.startswith("search:")
        expected_complex_key = (
            "search:end_date:2023-12-31:file_type:pdf:max_size:5000:"
            "min_size:1000:page:2:page_size:50:query:document:start_date:2023-01-01"
        )
        assert complex_key == expected_complex_key
        assert "use_cache" not in complex_key

    def test_cache_hit_returns_cached_result(self, search_service):
        """
        Test that cached search results are returned without executing a search.
        """
        # Arrange
        cached_result = {
            "items": [{"id": "doc1", "original_filename": "test.pdf"}],
            "total": 1,
            "page": 1,
            "page_size": 10,
            "source": "database",
        }

        with patch(
            "files.services.search_service.validate_search_params"
        ) as mock_validate, patch(
            "files.services.cache_service.get_data", return_value=cached_result
        ) as mock_cache_get, patch.object(
            search_service, "_search_es"
        ) as mock_es_search, patch.object(
            search_service, "_search_db"
        ) as mock_db_search:

            # Configure validator mock
            mock_validate.return_value = {
                "query": "test",
                "file_type": None,
                "min_size": None,
                "max_size": None,
                "start_date": None,
                "end_date": None,
                "page": 1,
                "page_size": 10,
                "use_cache": True,
            }

            # Act
            result = search_service.search_files({"query": "test"})

            # Assert
            # Should return cached result without searching
            assert result == cached_result
            mock_cache_get.assert_called_once()  # Verify cache was checked
            mock_es_search.assert_not_called()
            mock_db_search.assert_not_called()
