import pytest
from files.exceptions import FileError, FileIntegrityError, FileMissingError, FileValidationError


class TestFileExceptions:
    """Tests for the custom file exceptions"""
    
    def test_file_error_base_exception(self):
        # Arrange
        message = "General file error"
        
        # Act
        error = FileError(message)
        
        # Assert
        assert str(error) == message
        assert isinstance(error, Exception)
    
    def test_file_integrity_error_inherits_from_file_error(self):
        # Arrange
        message = "Hash collision detected"
        
        # Act
        error = FileIntegrityError(message)
        
        # Assert
        assert str(error) == message
        assert isinstance(error, FileError)
    
    def test_file_missing_error_inherits_from_file_error(self):
        # Arrange
        message = "File not found in storage"
        
        # Act
        error = FileMissingError(message)
        
        # Assert
        assert str(error) == message
        assert isinstance(error, FileError)
    
    def test_file_validation_error_inherits_from_file_error(self):
        # Arrange
        message = "File extension not allowed"
        
        # Act
        error = FileValidationError(message)
        
        # Assert
        assert str(error) == message
        assert isinstance(error, FileError)
    
    def test_exception_hierarchy(self):
        # Arrange
        file_error = FileError("Base error")
        integrity_error = FileIntegrityError("Integrity error")
        missing_error = FileMissingError("Missing error")
        validation_error = FileValidationError("Validation error")
        
        # Act & Assert - Test exception hierarchy
        assert isinstance(file_error, Exception)
        assert isinstance(integrity_error, FileError) 
        assert isinstance(missing_error, FileError)
        assert isinstance(validation_error, FileError)
        
        # They should all be catchable with FileError
        try:
            raise integrity_error
        except FileError as e:
            assert e is integrity_error
            
        try:
            raise missing_error
        except FileError as e:
            assert e is missing_error
            
        try:
            raise validation_error
        except FileError as e:
            assert e is validation_error
