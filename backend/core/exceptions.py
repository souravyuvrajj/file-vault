from rest_framework.response import Response
from rest_framework import status
from rest_framework.views import exception_handler
from files.exceptions import (
    FileError,
    FileIntegrityError,
    FileMissingError as ServiceMissing,
)


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        return response

    if isinstance(exc, ServiceMissing):
        return Response({"detail": str(exc)}, status=status.HTTP_404_NOT_FOUND)
    if isinstance(exc, FileIntegrityError):
        return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
    if isinstance(exc, FileError):
        return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

    return response
