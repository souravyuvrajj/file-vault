from unittest.mock import MagicMock, patch

import pytest
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from files.models import File

# Now we can import Django-specific modules
from files.serializers import FileSerializer


class TestFileValidation:
    """
    Tests for file validation in the system.

    These tests verify:
    - Validation of file types
    - Validation of file sizes
    - Validation of filenames
    """

    def test_reject_disallowed_file_type(self):
        """
        Test that disallowed file types are rejected.

        Strategy:
        1. Create a validator with limited allowed types
        2. Try to validate a disallowed type
        3. Verify ValidationError is raised

        Expected behavior:
        - Should raise ValidationError with appropriate message
        """
        # Arrange
        serializer = FileSerializer()
        disallowed_type = "exe"
        allowed_types = ["pdf", "txt", "jpg"]

        # Act & Assert
        with patch("files.serializers.getattr") as mock_getattr:
            # Configure getattr to return our allowed_types
            mock_getattr.return_value = allowed_types

            with pytest.raises(ValidationError) as excinfo:
                serializer.validate_file_type(disallowed_type)

            # Verify error message
            error_msg = str(excinfo.value)
            assert "File type not allowed" in error_msg
            assert "pdf" in error_msg
            assert "txt" in error_msg
            assert "jpg" in error_msg

            # Verify getattr was called to fetch ALLOWED_FILE_TYPES
            mock_getattr.assert_called_once()

    def test_allow_valid_file_type(self):
        """
        Test that allowed file types pass validation.

        Strategy:
        1. Create a validator with specific allowed types
        2. Try to validate an allowed type
        3. Verify no exception is raised and type is returned

        Expected behavior:
        - Should return the lowercased file type
        """
        # Arrange
        serializer = FileSerializer()
        allowed_type = "PDF"  # Will be lowercased
        allowed_types = ["pdf", "txt", "jpg"]

        # Act & Assert
        with patch("files.serializers.getattr") as mock_getattr:
            # Configure getattr to return our allowed_types
            mock_getattr.return_value = allowed_types

            result = serializer.validate_file_type(allowed_type)

            # Verify the type is lowercased and returned
            assert result == "pdf"

            # Verify getattr was called to fetch ALLOWED_FILE_TYPES
            mock_getattr.assert_called_once()

    def test_empty_allowed_types_passes_all_types(self):
        """
        Test that any file type passes validation when allowed_types is empty.

        Strategy:
        1. Create a validator with empty allowed types list
        2. Try to validate any type
        3. Verify no exception is raised

        Expected behavior:
        - Should return the file type (any type is allowed when list is empty)
        """
        # Arrange
        serializer = FileSerializer()
        test_type = "any_type"

        # Act & Assert
        with patch("files.serializers.getattr") as mock_getattr:
            # Configure getattr to return empty list (all types allowed)
            mock_getattr.return_value = []

            result = serializer.validate_file_type(test_type)

            # Verify the type is returned
            assert result == test_type.lower()

            # Verify getattr was called to fetch ALLOWED_FILE_TYPES
            mock_getattr.assert_called_once()
