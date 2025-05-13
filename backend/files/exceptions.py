class FileError(Exception):
    """Base class for all file-related errors."""

    pass


class FileIntegrityError(FileError):
    """Hash collision or integrity check failed."""

    pass


class FileMissingError(FileError):
    """File not found in storage or DB."""

    pass


class FileValidationError(FileError):
    """Raised when an uploaded file fails validation (size, name, extension)."""

    pass
