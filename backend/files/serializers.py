import os
from django.conf import settings
from rest_framework import serializers
from .models import File


class FileSerializer(serializers.ModelSerializer):
    file = serializers.FileField(write_only=True, help_text="The file to upload")
    file_size = serializers.IntegerField(source="size", read_only=True)

    class Meta:
        model = File
        fields = [
            "id",
            "file",
            "original_filename",
            "file_type",
            "file_size",
            "uploaded_at",
            "ref_count",
        ]
        read_only_fields = [
            "id",
            "original_filename",
            "file_type",
            "file_size",
            "uploaded_at",
            "ref_count",
        ]

    def validate_file(self, file_obj):
        max_size = settings.FILE_UPLOAD_MAX_MEMORY_SIZE
        if file_obj.size > max_size:
            raise serializers.ValidationError(
                f"File too large ({file_obj.size} bytes; max {max_size})"
            )

        name = file_obj.name
        if any(sep in name for sep in ("..", "/", "\\")):
            raise serializers.ValidationError(
                "Invalid filename; contains path segments"
            )

        if len(name) > settings.MAX_FILENAME_LENGTH:
            raise serializers.ValidationError(
                f"Filename too long (max {settings.MAX_FILENAME_LENGTH} chars)"
            )

        ext = os.path.splitext(name)[1].lower().lstrip(".")
        allowed = settings.ALLOWED_FILE_EXTENSIONS
        if allowed and ext not in allowed:
            raise serializers.ValidationError(
                f"Extension '{ext}' not allowed: {allowed}"
            )

        return file_obj


from datetime import date
from rest_framework import serializers


MULTIPLIERS = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3}


class FileSearchParamsSerializer(serializers.Serializer):
    filename = serializers.CharField(
        min_length=2, required=False, help_text="Search term in filename"
    )
    file_extension = serializers.CharField(
        required=False, help_text="Extension without dot, e.g. 'pdf'"
    )
    min_size = serializers.IntegerField(
        min_value=0, required=False, help_text="Minimum size in bytes"
    )
    max_size = serializers.IntegerField(
        min_value=0, required=False, help_text="Maximum size in bytes"
    )
    start_date = serializers.DateField(required=False, help_text="Upload date (From)")
    end_date = serializers.DateField(required=False, help_text="Upload date (To)")
    page = serializers.IntegerField(min_value=1, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)

    def validate(self, data):
        # 1) Size range sanity
        min_s = data.get("min_size")
        max_s = data.get("max_size")
        if min_s is not None and max_s is not None and min_s > max_s:
            raise serializers.ValidationError("min_size cannot exceed max_size")

        # 2) Date range sanity
        sd = data.get("start_date")
        ed = data.get("end_date")
        if sd and ed and sd > ed:
            raise serializers.ValidationError("start_date cannot be after end_date")

        # 3) Normalize empty strings → None
        for key in ("filename", "file_extension"):
            if data.get(key, "").strip() == "":
                data[key] = None

        return data