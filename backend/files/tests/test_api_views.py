"""
Tests for API views.
"""

from unittest.mock import MagicMock, mock_open, patch

import pytest
from files.exceptions import FileNotFoundError, FileValidationError
from files.repository.file_repository import FileRepository
from files.services.file_service import FileService
from files.services.search_service import SearchService
from files.use_cases.file_upload import UploadFileUseCase
from rest_framework import status


@pytest.fixture
def mock_upload_use_case():
    """Create a mock UploadFileUseCase."""
    with patch("files.views.UploadFileUseCase") as MockUseCase:
        mock_use_case = MagicMock()
        MockUseCase.return_value = mock_use_case
        yield mock_use_case


@pytest.fixture
def mock_file_repository():
    """Create a mock FileRepository."""
    with patch("files.views.DjangoFileRepository") as MockRepo:
        mock_repo = MagicMock()
        MockRepo.return_value = mock_repo
        yield mock_repo


@pytest.fixture
def mock_search_service():
    """Create a mock SearchService."""
    with patch("files.views.SearchService") as MockService:
        mock_service = MagicMock()
        MockService.return_value = mock_service
        yield mock_service


class TestFileUploadView:
    """Tests for file upload view."""

    @pytest.mark.parametrize(
        "is_new_upload, expected_status_code, file_id, initial_ref_count, expected_ref_count",
        [
            (
                True,
                status.HTTP_201_CREATED,
                "new_file_id",
                0,
                1,
            ),  # For a new file, initial_ref_count isn't strictly used by mock, but conceptually it's 0 before upload
            (
                False,
                status.HTTP_200_OK,
                "existing_file_id",
                1,
                2,
            ),  # For a duplicate, ref_count increments from its existing value
        ],
    )
    def test_upload_successful(
        self,
        client,
        sample_file,
        mock_upload_use_case,
        is_new_upload,
        expected_status_code,
        file_id,
        initial_ref_count,
        expected_ref_count,
    ):
        """Test successful upload of a new or duplicate file."""
        # Arrange
        mock_file_data = MagicMock()
        mock_file_data.id = file_id
        mock_file_data.original_filename = "test_file.txt"
        mock_file_data.file_type = "text/plain"
        mock_file_data.uploaded_at.isoformat.return_value = "2023-01-01T00:00:00Z"
        mock_file_data.size = 100
        mock_file_data.ref_count = (
            expected_ref_count  # This is the ref_count *after* the use case has run
        )

        # Mock the use case execution
        # The use case returns the file object and a boolean indicating if it's new
        mock_upload_use_case.execute.return_value = (mock_file_data, is_new_upload)

        # Act
        response = client.post(
            "/api/files/upload/", {"file": sample_file}, format="multipart"
        )

        # Assert
        assert response.status_code == expected_status_code
        assert response.json()["id"] == file_id
        assert response.json()["is_new"] is is_new_upload
        assert response.json()["ref_count"] == expected_ref_count
        mock_upload_use_case.execute.assert_called_once()

    def test_upload_missing_file(self, client, mock_upload_use_case):
        """Test upload endpoint with missing file."""
        # Act
        response = client.post("/api/files/upload/", {}, format="multipart")

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()
        assert "No file provided" in response.json()["error"]
        assert not mock_upload_use_case.execute.called

    def test_upload_validation_error(self, client, sample_file, mock_upload_use_case):
        """Test upload with validation error."""
        # Arrange
        mock_upload_use_case.execute.side_effect = FileValidationError(
            "File validation failed"
        )

        # Act
        response = client.post(
            "/api/files/upload/", {"file": sample_file}, format="multipart"
        )

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()
        assert "File validation failed" in response.json()["error"]
        mock_upload_use_case.execute.assert_called_once()


class TestGetFileView:
    """Tests for get file view."""

    def test_get_file_success(self, client, mock_file_repository):
        """Test successful file retrieval."""
        # Arrange
        file_id = "test-file-id"
        mock_file = MagicMock()
        mock_file.original_filename = "test_file.txt"
        mock_file.file_type = "text/plain"
        mock_file.size = 100
        mock_file.content = b"Test file content"

        # Setup file.read() to return the test content
        mock_file.file = MagicMock()
        mock_file.file.read.return_value = b"Test file content"
        mock_file.file.open = MagicMock()
        mock_file.file.close = MagicMock()

        mock_file_repository.get_by_id.return_value = mock_file

        # Act
        response = client.get(f"/api/files/{file_id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "text/plain"
        assert response["Content-Disposition"] == 'attachment; filename="test_file.txt"'
        assert response.content == b"Test file content"
        mock_file_repository.get_by_id.assert_called_once_with(file_id)
        mock_file.file.open.assert_called_once_with("rb")
        mock_file.file.read.assert_called_once()
        mock_file.file.close.assert_called_once()

    def test_get_file_not_found(self, client, mock_file_repository):
        """Test file not found."""
        # Arrange
        file_id = "nonexistent-file-id"
        mock_file_repository.get_by_id.return_value = None

        # Act
        response = client.get(f"/api/files/{file_id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.json()
        mock_file_repository.get_by_id.assert_called_once_with(file_id)


class TestSearchFilesView:
    """Tests for search files view."""

    def test_search_files_success(self, client, mock_search_service):
        """Test successful file search."""
        # Arrange
        search_results = {
            "items": [
                {
                    "id": "file-1",
                    "original_filename": "file1.txt",
                    "file_type": "text/plain",
                    "uploaded_at": "2023-01-01T00:00:00Z",
                    "file_size": 100,
                    "ref_count": 1,
                }
            ],
            "total": 1,
            "page": 1,
            "page_size": 20,
            "source": "database",
        }

        mock_search_service.search_files.return_value = search_results

        # Act
        response = client.get("/api/files/search/?query=test&file_type=txt")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == search_results
        mock_search_service.search_files.assert_called_once()

        # Verify search parameters were passed correctly
        call_args = mock_search_service.search_files.call_args[0][0]
        assert call_args["query"] == "test"
        assert call_args["file_type"] == "txt"

    def test_search_files_validation_error(self, client, mock_search_service):
        """Test search with validation error."""
        # Arrange
        mock_search_service.search_files.side_effect = FileValidationError(
            "Invalid search parameters"
        )

        # Act
        response = client.get("/api/files/search/?q=t")  # Too short query

        # Assert
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "error" in response.json()
        assert "Invalid search parameters" in response.json()["error"]
        mock_search_service.search_files.assert_called_once()


class TestStorageSummaryView:
    """Tests for storage summary view."""

    def test_storage_summary_success(self, client, mock_file_repository):
        """Test successful storage summary retrieval."""
        # Arrange
        summary = {
            "total_files": 10,
            "total_size": 1024000,
            "deduplicated_size": 512000,
            "storage_saved": 512000,
            "savings_percent": 50.0,
        }

        mock_file_repository.get_storage_summary.return_value = summary

        # Act
        response = client.get("/api/files/storage-summary/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json() == summary
        mock_file_repository.get_storage_summary.assert_called_once()


class TestFileDetailView:
    """Tests for file detail view which handles both GET (download) and DELETE operations."""

    def test_download_file_success(self, client, mock_file_repository):
        """Test successful file download."""
        # Arrange
        file_id = "test-file-id"
        mock_file = MagicMock()
        mock_file.original_filename = "test_file.txt"
        mock_file.file_type = "text/plain"
        mock_file.size = 100
        mock_file.file = MagicMock()
        mock_file.file.open = mock_open(read_data=b"Test file content")
        mock_file.file.read.return_value = b"Test file content"

        mock_file_repository.get_by_id.return_value = mock_file

        # Act
        response = client.get(f"/api/files/{file_id}/download/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response["Content-Type"] == "text/plain"
        assert response["Content-Disposition"] == 'attachment; filename="test_file.txt"'
        mock_file_repository.get_by_id.assert_called_once_with(file_id)
        mock_file.file.open.assert_called_once_with("rb")
        mock_file.file.close.assert_called_once()

    def test_download_file_not_found(self, client, mock_file_repository):
        """Test file download when file is not found."""
        # Arrange
        file_id = "nonexistent-file-id"
        mock_file_repository.get_by_id.return_value = None

        # Act
        response = client.get(f"/api/files/{file_id}/download/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.json()
        mock_file_repository.get_by_id.assert_called_once_with(file_id)

    @pytest.fixture
    def mock_file_service(self):
        """Create a mock FileService."""
        with patch("files.views.FileService") as MockService:
            mock_service = MagicMock()
            MockService.return_value = mock_service
            yield mock_service

    def test_delete_file_success(self, client, mock_file_repository, mock_file_service):
        """Test successful file deletion."""
        # Arrange
        file_id = "test-file-id"
        mock_file_service.delete_file.return_value = True

        # Act
        response = client.delete(f"/api/files/{file_id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "success"
        assert "deleted successfully" in response.json()["message"]
        mock_file_service.delete_file.assert_called_once_with(file_id)

    def test_delete_file_decrement_ref_count(
        self, client, mock_file_repository, mock_file_service
    ):
        """Test file deletion that only decrements reference count."""
        # Arrange
        file_id = "test-file-id"
        mock_file_service.delete_file.return_value = False

        # Act
        response = client.delete(f"/api/files/{file_id}/")

        # Assert
        assert response.status_code == status.HTTP_200_OK
        assert response.json()["status"] == "success"
        assert "reference count decremented" in response.json()["message"]
        mock_file_service.delete_file.assert_called_once_with(file_id)

    def test_delete_file_not_found(
        self, client, mock_file_repository, mock_file_service
    ):
        """Test file deletion when file is not found."""
        # Arrange
        file_id = "nonexistent-file-id"
        mock_file_service.delete_file.side_effect = FileNotFoundError(
            f"File with ID {file_id} not found"
        )

        # Act
        response = client.delete(f"/api/files/{file_id}/")

        # Assert
        assert response.status_code == status.HTTP_404_NOT_FOUND
        assert "error" in response.json()
        assert f"File with ID {file_id} not found" in response.json()["error"]
        mock_file_service.delete_file.assert_called_once_with(file_id)
