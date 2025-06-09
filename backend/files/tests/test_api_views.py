import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from django.core.files.uploadedfile import SimpleUploadedFile
from files.models import File
from unittest.mock import patch
from files.exceptions import FileError, FileIntegrityError


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def sample_file():
    return SimpleUploadedFile(
        name="test.txt",
        content=b"test content",
        content_type="text/plain"
    )


@pytest.fixture
def oversized_file(settings):
    max_size = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
    content = b"a" * (max_size + 1)
    return SimpleUploadedFile(
        name="big.bin",
        content=content,
        content_type="application/octet-stream"
    )


@pytest.mark.django_db
class TestFileUpload:
    def test_successful_new_file_upload_returns_201(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        
        # Act
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        
        # Assert
        assert response.status_code == status.HTTP_201_CREATED

    def test_successful_new_file_upload_creates_db_entry(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        initial_count = File.objects.count()
        
        # Act
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        
        # Assert
        assert File.objects.count() == initial_count + 1

    def test_duplicate_file_upload_returns_200(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        api_client.post(url, {"file": sample_file}, format="multipart")
        sample_file.seek(0)
        
        # Act
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        
        # Assert
        assert response.status_code == status.HTTP_200_OK

    def test_duplicate_file_upload_increments_ref_count(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        api_client.post(url, {"file": sample_file}, format="multipart")
        sample_file.seek(0)
        
        # Act
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        
        # Assert
        assert response.json()["ref_count"] == 2

    @patch('files.services.file_service.FileManager.upload_file')
    def test_file_integrity_error_returns_409(self, mock_upload, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        mock_upload.side_effect = FileIntegrityError("Hash mismatch")
        
        # Act
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        
        # Assert
        assert response.status_code == status.HTTP_409_CONFLICT


@pytest.mark.django_db
class TestFileSearch:
    @pytest.fixture
    def setup_test_files(self, api_client, tmp_path):
        small_file = tmp_path / "small.txt"
        small_file.write_text("test")
        large_file = tmp_path / "large.txt"
        large_file.write_bytes(b"x" * 1024)
        
        url = reverse("file-list")
        for path in (small_file, large_file):
            with open(path, "rb") as fp:
                api_client.post(url, {"file": fp}, format="multipart")
        return small_file, large_file

    def test_list_all_files_returns_200(self, api_client, setup_test_files):
        # Arrange
        url = reverse("file-list")
        
        # Act
        response = api_client.get(url)
        
        # Assert
        assert response.status_code == status.HTTP_200_OK

    def test_filename_filter_returns_matching_files(self, api_client, setup_test_files):
        # Arrange
        url = reverse("file-list")
        
        # Act
        response = api_client.get(url, {"filename": "small"})
        
        # Assert
        assert all("small" in item["original_filename"] for item in response.json()["items"])

    def test_size_filter_returns_matching_files(self, api_client, setup_test_files):
        # Arrange
        url = reverse("file-list")
        
        # Act
        response = api_client.get(url, {"min_size": 1024})
        
        # Assert
        assert all(item["file_size"] >= 1024 for item in response.json()["items"])


@pytest.mark.django_db
class TestFileDelete:
    def test_delete_single_reference_marks_as_deleted(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        file_id = response.json()["id"]
        delete_url = reverse("file-detail", args=[file_id])
        
        # Act
        response = api_client.delete(delete_url)
        
        # Assert
        assert response.json()["status"] == "deleted"

    def test_delete_with_multiple_references_decrements_count(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        sample_file.seek(0)
        api_client.post(url, {"file": sample_file}, format="multipart")
        file_id = response.json()["id"]
        delete_url = reverse("file-detail", args=[file_id])
        
        # Act
        response = api_client.delete(delete_url)
        
        # Assert
        assert response.json()["status"] == "ref_count decremented"


@pytest.mark.django_db
class TestFileDownload:
    def test_download_existing_file_returns_200(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        file_id = response.json()["id"]
        download_url = reverse("file-download", args=[file_id])
        
        # Act
        response = api_client.get(download_url)
        
        # Assert
        assert response.status_code == status.HTTP_200_OK

    def test_download_includes_content_disposition(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        response = api_client.post(url, {"file": sample_file}, format="multipart")
        file_id = response.json()["id"]
        download_url = reverse("file-download", args=[file_id])
        
        # Act
        response = api_client.get(download_url)
        
        # Assert
        assert "attachment" in response["Content-Disposition"]


@pytest.mark.django_db
class TestStorageSummary:
    def test_storage_summary_with_duplicates_shows_savings(self, api_client, sample_file):
        # Arrange
        url = reverse("file-list")
        api_client.post(url, {"file": sample_file}, format="multipart")
        sample_file.seek(0)
        api_client.post(url, {"file": sample_file}, format="multipart")
        summary_url = reverse("file-storage-summary")
        
        # Act
        response = api_client.get(summary_url)
        data = response.json()
        
        # Assert
        assert data["savings_percentage"] == pytest.approx(50.0)
