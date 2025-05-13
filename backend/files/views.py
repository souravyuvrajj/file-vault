# files/views.py

import logging
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotFound, ValidationError, APIException
from rest_framework.response import Response
from django.http import FileResponse

from files.models import File
from files.exceptions import FileError, FileIntegrityError, FileMissingError
from files.serializers import FileSerializer, FileSearchParamsSerializer
from files.services.file_service import FileManager
from files.services.search_service import SearchService

logger = logging.getLogger(__name__)


class FileViewSet(
    mixins.ListModelMixin,      # GET  /api/files/
    mixins.CreateModelMixin,    # POST /api/files/
    mixins.RetrieveModelMixin,  # GET  /api/files/{id}/
    mixins.DestroyModelMixin,   # DELETE /api/files/{id}/
    viewsets.GenericViewSet,
):
    """
    Database-only File API:
      - list       → search via SearchService
      - create     → upload & dedupe
      - retrieve   → metadata
      - destroy    → delete/ref-count
      - download   → file download
      - storage-summary → dedupe stats
    """
    queryset = File.objects.filter(is_deleted=False).order_by("-uploaded_at")
    serializer_class = FileSerializer
    lookup_field = "id"

    file_manager = FileManager(hash_algorithm="md5")
    search_service = SearchService()

    def list(self, request, *args, **kwargs):
        # 1) Validate & normalize search params
        params = FileSearchParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        pd = params.validated_data

        # 2) Delegate filtering + pagination to SearchService
        try:
            result = self.search_service.search(pd)
        except Exception as e:
            logger.error("Search failed: %s", e)
            raise APIException("Could not perform search")

        return Response(result, status=status.HTTP_200_OK)

    def create(self, request, *args, **kwargs):
        # 1) Validate file via serializer
        serializer = FileSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        file_obj = serializer.validated_data["file"]

        # 2) Upload & dedupe
        try:
            instance, is_new = self.file_manager.upload_file(
                file_obj, file_obj.name, file_obj.content_type
            )
        except FileIntegrityError as e:
            return Response({"detail": str(e)}, status=status.HTTP_409_CONFLICT)
        except FileError as e:
            raise ValidationError(str(e))

        # 3) Respond with serialized data + is_new flag
        out = FileSerializer(instance).data
        out["is_new"] = is_new
        code = status.HTTP_201_CREATED if is_new else status.HTTP_200_OK
        return Response(out, status=code)

    def destroy(self, request, *args, **kwargs):
        """
        Override the default destroy() to use FileManager.delete_file(),
        which decrements ref_count and only soft-deletes when ref_count hits zero.
        """
        file_obj = self.get_object()  # ensures pk exists & is_deleted=False
        try:
            fully_deleted = self.file_manager.delete_file(file_obj.id)
        except FileMissingError as e:
            raise NotFound(str(e))
        except FileError as e:
            raise APIException(str(e))

        # Return whether we merely decremented the count or actually deleted
        status_msg = "deleted" if fully_deleted else "ref_count decremented"
        return Response({"status": status_msg}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def download(self, request, id=None):
        # GET /api/files/{id}/download/
        try:
            f = self.file_manager.get_file(id)
        except FileMissingError as e:
            raise NotFound(str(e))
        return FileResponse(
            f.file.open("rb"), as_attachment=True, filename=f.original_filename
        )

    @action(detail=False, methods=["get"], url_path="storage-summary")
    def storage_summary(self, request):
        # GET /api/files/storage-summary/
        try:
            summary = self.file_manager.get_storage_summary()
        except Exception as e:
            logger.error("Storage summary error: %s", e)
            raise APIException("Could not compute storage summary")
        return Response(summary, status=status.HTTP_200_OK)
