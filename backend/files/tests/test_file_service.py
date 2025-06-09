import pytest
import uuid
from unittest.mock import Mock, patch
from io import BytesIO
from django.db import IntegrityError

from files.services.file_service import FileManager
from files.models import File
from files.exceptions import FileError, FileIntegrityError, FileMissingError


@pytest.fixture
def file_manager():
    """Create a FileManager instance for testing"""
    return FileManager()


@pytest.fixture
def sample_file_content():
    """Create a fresh BytesIO object simulating a file for each test
    
    This fixture creates a new object for each test to prevent shared file pointer state.
    No need to call seek(0) when using this fixture across tests.
    """
    def _create_fresh_file():
        content = b"test file content"
        file_obj = BytesIO(content)
        file_obj.size = len(content)
        file_obj.name = "test.txt"
        return file_obj
        
    return _create_fresh_file()


@pytest.mark.django_db
class TestComputeHash:
    def test_compute_hash_sha256(self, file_manager, sample_file_content):
        # Arrange
        expected_hash = "60f5237ed4049f0382661ef009d2bc42e48c3ceb3edb6600f7024e7ab3b838f3"
        
        # Act
        result = file_manager._compute_hash(sample_file_content)
        
        # Assert
        assert result == expected_hash
        
    def test_compute_hash_md5(self):
        # Arrange
        file_manager = FileManager(hash_algorithm="md5")
        content = b"test file content"
        file_obj = BytesIO(content)
        file_obj.size = len(content)
        expected_hash = "c785060c866796cc2a1708c997154c8e"
        
        # Act
        result = file_manager._compute_hash(file_obj)
        
        # Assert
        assert result == expected_hash
        
    def test_compute_hash_maintains_file_pointer_position(self, file_manager, sample_file_content):
        # Arrange
        initial_position = 5
        sample_file_content.seek(initial_position)
        
        # Act
        file_manager._compute_hash(sample_file_content)
        
        # Assert
        assert sample_file_content.tell() == initial_position, "File position should be preserved after hash computation"


@pytest.mark.django_db
class TestUploadFile:
    def test_upload_empty_file(self, file_manager):
        # Arrange
        empty_file = BytesIO(b"")
        empty_file.size = 0
        empty_file.name = "empty.txt"
        filename = "empty.txt"
        file_type = "text/plain"
        
        # Act
        result, is_new = file_manager.upload_file(empty_file, filename, file_type)
        
        # Assert
        assert is_new is True
        assert result.original_filename == filename
        assert result.file_type == file_type
        assert result.size == 0
        assert result.ref_count == 1
    
    def test_upload_new_file_creates_file_object(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        
        # Act
        result, is_new = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Assert
        assert is_new is True
        assert result.original_filename == filename
        assert result.file_type == file_type
        assert result.size == sample_file_content.size
        assert result.ref_count == 1

    def test_upload_duplicate_file_increments_ref_count(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        # First upload
        first_file, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Act - create a fresh copy for second upload
        fresh_content = sample_file_content = BytesIO(b"test file content")
        fresh_content.size = len(b"test file content")
        fresh_content.name = "test.txt"
        second_file, is_new = file_manager.upload_file(fresh_content, "different.txt", file_type)
        
        # Assert
        assert is_new is False
        assert second_file.id == first_file.id
        assert second_file.ref_count == 2
        
    @patch('files.models.File.objects.filter')
    @patch('files.models.File.objects.get')
    def test_upload_with_integrity_error_recovers_and_increments(self, mock_get, mock_filter, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        
        # Mock existing file query
        mock_existing = Mock()
        mock_existing.id = uuid.uuid4()
        mock_existing.ref_count = 1
        mock_existing.increment_ref_count.return_value = None
        
        mock_filter.return_value.exists.return_value = True
        mock_filter.return_value.first.return_value = mock_existing
        mock_get.return_value = mock_existing
        
        # Make save raise IntegrityError on first call but succeed on second
        with patch('django.db.models.Model.save', side_effect=IntegrityError("Duplicate key")):
            # Act
            result, is_new = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Assert
        assert is_new is False
        assert result.id == mock_existing.id
        mock_existing.increment_ref_count.assert_called_once()
        
    @patch('files.models.File.objects.get')
    def test_upload_with_integrity_error_but_no_existing_file_raises_error(self, mock_get, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        
        # Make get raise DoesNotExist
        mock_get.side_effect = File.DoesNotExist()
        
        # Act & Assert
        with patch('django.db.models.Model.save', side_effect=IntegrityError("Duplicate key")):
            with pytest.raises(FileIntegrityError):
                file_manager.upload_file(sample_file_content, filename, file_type)
    
    @patch('files.models.File.increment_ref_count')
    def test_upload_with_lock_error_raises_file_error(self, mock_increment, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        mock_increment.side_effect = RuntimeError("Lock error")
        
        # First create a file that we can try to duplicate
        first_file, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Create a fresh file with identical content for the second upload attempt
        fresh_content = BytesIO(b"test file content")
        fresh_content.size = len(b"test file content")
        fresh_content.name = "test.txt"
        
        # Act & Assert
        with pytest.raises(FileError, match="Concurrent update error"):
            file_manager.upload_file(fresh_content, filename, file_type)


@pytest.mark.django_db
class TestDeleteFile:
    def test_delete_file_with_ref_count_one_marks_deleted(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Act
        result = file_manager.delete_file(file_obj.id)
        
        # Assert
        assert result is True
        deleted_file = File.objects.get(pk=file_obj.id)
        assert deleted_file.is_deleted is True
        # Note: The implementation seems to keep ref_count at 1 even when deleted
        assert deleted_file.ref_count == 1
        
    def test_delete_file_with_multiple_refs_decrements_count(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Create a fresh identical file for the second upload
        fresh_content = BytesIO(b"test file content")
        fresh_content.size = len(b"test file content")
        fresh_content.name = "test.txt"
        file_manager.upload_file(fresh_content, filename, file_type)  # Increment ref_count
        
        # Act
        result = file_manager.delete_file(file_obj.id)
        
        # Assert
        assert result is False
        updated_file = File.objects.get(pk=file_obj.id)
        assert updated_file.is_deleted is False
        assert updated_file.ref_count == 1
    
    def test_delete_nonexistent_file_raises_file_missing_error(self, file_manager):
        # Arrange
        nonexistent_id = uuid.uuid4()
        
        # Act & Assert
        with pytest.raises(FileMissingError):
            file_manager.delete_file(nonexistent_id)
    
    def test_delete_already_deleted_file_raises_file_missing_error(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        file_manager.delete_file(file_obj.id)  # Mark as deleted
        
        # Act & Assert
        with pytest.raises(FileMissingError):
            file_manager.delete_file(file_obj.id)
    
    @patch('files.models.File.decrement_ref_count')
    def test_delete_with_lock_error_raises_file_error(self, mock_decrement, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        mock_decrement.side_effect = RuntimeError("Lock error")
        
        # Act & Assert
        with pytest.raises(FileError, match="Concurrent update error"):
            file_manager.delete_file(file_obj.id)


@pytest.mark.django_db
class TestGetStorageSummary:
    def test_empty_storage_returns_zero_values(self, file_manager):
        # Arrange - no files in the system
        
        # Act
        result = file_manager.get_storage_summary()
        
        # Assert
        assert result["total_file_size"] == 0
        assert result["deduplicated_storage"] == 0
        assert result["storage_saved"] == 0
        assert result["savings_percentage"] == 0
    
    def test_single_file_no_savings(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        expected_size = sample_file_content.size
        
        # Act
        result = file_manager.get_storage_summary()
        
        # Assert
        assert result["total_file_size"] == expected_size
        assert result["deduplicated_storage"] == expected_size
        assert result["storage_saved"] == 0
        assert result["savings_percentage"] == 0
    
    def test_duplicate_files_show_savings(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Add duplicate with fresh content (same data)
        fresh_content = BytesIO(b"test file content")
        fresh_content.size = len(b"test file content")
        fresh_content.name = "test.txt"
        file_manager.upload_file(fresh_content, "duplicate.txt", file_type)
        
        expected_size = sample_file_content.size
        
        # Act
        result = file_manager.get_storage_summary()
        
        # Assert
        assert result["total_file_size"] == expected_size * 2
        assert result["deduplicated_storage"] == expected_size
        assert result["storage_saved"] == expected_size
        assert result["savings_percentage"] == 50.0
    
    def test_different_files_show_correct_totals(self, file_manager, sample_file_content):
        # Arrange
        # First file
        file_manager.upload_file(sample_file_content, "test1.txt", "text/plain")
        size1 = sample_file_content.size
        
        # Second different file
        content2 = b"different content"
        file_obj2 = BytesIO(content2)
        file_obj2.size = len(content2)
        file_manager.upload_file(file_obj2, "test2.txt", "text/plain")
        size2 = file_obj2.size
        
        # Act
        result = file_manager.get_storage_summary()
        
        # Assert
        assert result["total_file_size"] == size1 + size2
        assert result["deduplicated_storage"] == size1 + size2
        assert result["storage_saved"] == 0
        assert result["savings_percentage"] == 0


@pytest.mark.django_db
class TestGetFile:
    def test_get_existing_file_returns_file(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        
        # Act
        result = file_manager.get_file(file_obj.id)
        
        # Assert
        assert result.id == file_obj.id
        assert result.original_filename == filename
    
    def test_get_nonexistent_file_raises_file_missing_error(self, file_manager):
        # Arrange
        nonexistent_id = uuid.uuid4()
        
        # Act & Assert
        with pytest.raises(FileMissingError):
            file_manager.get_file(nonexistent_id)
    
    def test_get_deleted_file_raises_file_missing_error(self, file_manager, sample_file_content):
        # Arrange
        filename = "test.txt"
        file_type = "text/plain"
        file_obj, _ = file_manager.upload_file(sample_file_content, filename, file_type)
        file_manager.delete_file(file_obj.id)  # Mark as deleted
        
        # Act & Assert
        with pytest.raises(FileMissingError):
            file_manager.get_file(file_obj.id)
