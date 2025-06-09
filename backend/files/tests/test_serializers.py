import os
import pytest
from unittest.mock import Mock, patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.conf import settings
from datetime import date
from rest_framework import serializers
from files.serializers import FileSerializer, FileSearchParamsSerializer
from files.exceptions import FileValidationError


@pytest.fixture(autouse=True)
def override_settings(settings):
    """Override settings for consistent test behavior"""
    settings.FILE_UPLOAD_MAX_MEMORY_SIZE = 10  # bytes
    settings.MAX_FILENAME_LENGTH = 20  # Increased to allow other validations to be tested
    settings.ALLOWED_FILE_EXTENSIONS = ["txt"]
    yield


class TestFileSerializerValidation:
    """Tests for FileSerializer.validate_file method"""
    
    def test_validate_file_too_large(self):
        # Arrange
        serializer = FileSerializer()
        big = SimpleUploadedFile("a.txt", b"0123456789" * 2)  # 20 bytes, twice max size
        
        # Act & Assert
        with pytest.raises(Exception) as e:
            serializer.validate_file(big)
        assert "File too large" in str(e.value)
        
    def test_validate_file_at_max_size_boundary(self):
        # Arrange
        serializer = FileSerializer()
        # Create a file exactly at the max size (10 bytes per settings fixture)
        exact_max = SimpleUploadedFile("a.txt", b"0123456789")  # 10 bytes
        
        # Act
        result = serializer.validate_file(exact_max)
        
        # Assert
        assert result == exact_max  # Should pass validation
    
    def test_validate_file_bad_name_segments_with_dots(self):
        # Arrange
        # Create a mocked file object with the problematic name
        mock_file = Mock()
        mock_file.name = "../evil.txt"
        mock_file.size = 5
        serializer = FileSerializer()
        
        # Act & Assert - Test observable behavior
        with pytest.raises(serializers.ValidationError) as excinfo:
            serializer.validate_file(mock_file)
        
        # Verify the correct error message is in the exception
        assert "Invalid filename" in str(excinfo.value)
    
    def test_validate_file_bad_name_segments_with_slash(self):
        # Arrange
        # Create a mocked file object with the problematic name
        mock_file = Mock()
        mock_file.name = "some/path/file.txt"
        mock_file.size = 5
        serializer = FileSerializer()
        
        # Act & Assert - Test observable behavior
        with pytest.raises(serializers.ValidationError) as excinfo:
            serializer.validate_file(mock_file)
        
        # Verify the correct error message is in the exception
        assert "Invalid filename" in str(excinfo.value)
    
    def test_validate_file_bad_name_segments_with_backslash(self):
        # Arrange
        # Create a mocked file object with the problematic name
        mock_file = Mock()
        mock_file.name = "windows\\path\\file.txt"  # Use raw string to preserve backslashes
        mock_file.size = 5
        serializer = FileSerializer()
        
        # Act & Assert - Test observable behavior
        with pytest.raises(serializers.ValidationError) as excinfo:
            serializer.validate_file(mock_file)
        
        # Verify the correct error message is in the exception
        assert "Invalid filename" in str(excinfo.value)
    
    def test_validate_file_name_too_long(self):
        # Arrange
        serializer = FileSerializer()
        # Using a very long name that exceeds our increased length setting
        long_name = "abcdefghijklmnopqrstuvwxyz.txt"  # 26 chars + ext > 20 chars
        f = SimpleUploadedFile(long_name, b"ok")
        
        # Act & Assert
        with pytest.raises(Exception) as e:
            serializer.validate_file(f)
        assert "Filename too long" in str(e.value)
    
    def test_validate_file_extension_not_allowed(self):
        # Arrange
        serializer = FileSerializer()
        good = SimpleUploadedFile("note.md", b"ok")
        
        # Act & Assert
        with pytest.raises(Exception) as e:
            serializer.validate_file(good)
        assert "Extension 'md' not allowed" in str(e.value)
    
    def test_validate_file_no_extension(self):
        # Arrange
        serializer = FileSerializer()
        no_ext = SimpleUploadedFile("noext", b"ok")
        
        # Act & Assert
        with pytest.raises(Exception) as e:
            serializer.validate_file(no_ext)
        assert "Extension '' not allowed" in str(e.value)
    
    def test_validate_file_success(self):
        # Arrange
        serializer = FileSerializer()
        ok = SimpleUploadedFile("ok.txt", b"ok")
        
        # Act
        result = serializer.validate_file(ok)
        
        # Assert
        assert result is ok


class TestFileSearchParamsSerializer:
    """Tests for FileSearchParamsSerializer"""
    
    @pytest.mark.parametrize("min_s,max_s,expected_valid", [
        (5, 1, False),  # min > max - invalid
        (None, 1, True),  # min not specified - valid
        (1, None, True),  # max not specified - valid
        (5, 10, True),  # min < max - valid
        (5, 5, True),  # min == max - valid
    ])
    def test_size_range_validation(self, min_s, max_s, expected_valid):
        # Arrange
        data = {}
        if min_s is not None:
            data["min_size"] = min_s
        if max_s is not None:
            data["max_size"] = max_s
        
        # Act
        serializer = FileSearchParamsSerializer(data=data)
        is_valid = serializer.is_valid()
        
        # Assert
        assert is_valid == expected_valid
        if not expected_valid:
            assert "min_size cannot exceed" in str(serializer.errors)
    
    @pytest.mark.parametrize(
        "sd,ed,expected_valid",
        [
            # Valid combinations
            (None, None, True),
            (date(2020, 1, 1), None, True),
            (None, date(2022, 12, 31), True),
            (date(2020, 1, 1), date(2022, 12, 31), True),
            # Invalid combinations
            (date(2022, 1, 1), date(2021, 1, 1), False),  # start > end
        ],
    )
    def test_date_range_validation(self, sd, ed, expected_valid):
        data = {}
        if sd:
            data["start_date"] = sd
        if ed:
            data["end_date"] = ed

        serializer = FileSearchParamsSerializer(data=data)
        assert serializer.is_valid() == expected_valid
        
    def test_multiple_validation_errors(self):
        # Test each validation error separately first
        # 1. Test min_size/max_size validation
        data = {
            "min_size": 100,
            "max_size": 50,  # Error: min_size > max_size
            "page": 1,  # Valid value to pass field validation
            "page_size": 20  # Valid value to pass field validation
        }
        serializer = FileSearchParamsSerializer(data=data)
        assert serializer.is_valid() is False
        assert "min_size cannot exceed max_size" in str(serializer.errors)
        
        # 2. Test date range validation
        data = {
            "start_date": date(2022, 5, 1),
            "end_date": date(2022, 4, 1),  # Error: start_date > end_date
            "page": 1,
            "page_size": 20
        }
        serializer = FileSearchParamsSerializer(data=data)
        assert serializer.is_valid() is False
        assert "start_date cannot be after end_date" in str(serializer.errors)
        
        # 3. Test field-level validations
        data = {
            "page": 0,  # Error: below min_value=1
            "page_size": 200  # Error: above max_value=100
        }
        serializer = FileSearchParamsSerializer(data=data)
        assert serializer.is_valid() is False
        assert "page" in serializer.errors
        assert "page_size" in serializer.errors
        
        # 4. Test that multiple field-level errors can occur simultaneously
        serializer = FileSearchParamsSerializer(data=data)
        assert serializer.is_valid() is False
        assert len(serializer.errors) == 2  # Both page and page_size errors
    
    def test_empty_strings_normalized_to_none(self):
        # Arrange - use valid filename that meets min_length=2 requirement
        # Omit file_extension since the blank check happens before our normalization
        data = {"filename": "ab"}
        
        # Act - manually run the validate method to test normalization
        serializer = FileSearchParamsSerializer(data=data)
        assert serializer.is_valid()
        # Add a blank space string after validation
        validated_data = serializer.validated_data.copy()
        validated_data["file_extension"] = "  "
        result = serializer.validate(validated_data)
        
        # Assert
        assert result["filename"] == "ab"  # Keep the valid value
        assert result["file_extension"] is None  # Empty string should be normalized to None
    
    def test_pagination_defaults(self):
        # Arrange
        data = {}  # Empty data
        
        # Act
        serializer = FileSearchParamsSerializer(data=data)
        
        # Assert
        assert serializer.is_valid()
        assert serializer.validated_data["page"] == 1
        assert serializer.validated_data["page_size"] == 20
    
    def test_custom_pagination_values(self):
        # Arrange
        data = {"page": 5, "page_size": 50}
        
        # Act
        serializer = FileSearchParamsSerializer(data=data)
        
        # Assert
        assert serializer.is_valid()
        assert serializer.validated_data["page"] == 5
        assert serializer.validated_data["page_size"] == 50
    
    def test_invalid_pagination_values(self):
        # Arrange
        data = {"page": 0, "page_size": 101}  # Invalid values
        
        # Act
        serializer = FileSearchParamsSerializer(data=data)
        
        # Assert
        assert not serializer.is_valid()
        assert "page" in serializer.errors
        assert "page_size" in serializer.errors
