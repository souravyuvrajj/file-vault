import os
import uuid
from uuid import uuid4
import logging

from django.core.files.storage import default_storage
from django.db import models, transaction
from django.db.models import F

logger = logging.getLogger(__name__)


def file_upload_path(instance, filename):
    ext = filename.rsplit(".", 1)[-1]
    name = uuid4().hex
    # partition into subfolders for scalability
    return os.path.join("uploads", name[:2], name[2:4], f"{name}.{ext}")


class File(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to=file_upload_path)
    file_hash = models.CharField(max_length=128, unique=True, db_index=True)
    size = models.BigIntegerField()
    uploaded_at = models.DateTimeField(auto_now_add=True)
    ref_count = models.PositiveIntegerField(default=1)
    original_filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20)
    is_deleted = models.BooleanField(default=False)
    version = models.PositiveIntegerField(default=0)

    class Meta:
        indexes = [
            models.Index(fields=["is_deleted", "uploaded_at"]),
            models.Index(fields=["file_hash"]),
        ]

    def save(self, *args, **kwargs):
        # auto-fill size/original fields on first save
        if not self.pk:
            self.size = self.file.size
            self.original_filename = self.original_filename or self.file.name
            self.file_type = self.file_type or self.original_filename.rsplit(".", 1)[-1]
        super().save(*args, **kwargs)

    @transaction.atomic
    def increment_ref_count(self):
        updated = File.objects.filter(pk=self.pk, version=self.version).update(
            ref_count=F("ref_count") + 1, version=F("version") + 1
        )
        if not updated:
            logger.error("Optimistic lock failed on increment for %s", self.id)
            raise RuntimeError("Concurrent update error")
        self.refresh_from_db()

    @transaction.atomic
    def decrement_ref_count(self):
        # lock the row
        obj = File.objects.select_for_update().get(pk=self.pk)
        if obj.ref_count > 1:
            updated = File.objects.filter(pk=self.pk, version=self.version).update(
                ref_count=F("ref_count") - 1, version=F("version") + 1
            )
            if not updated:
                logger.error("Optimistic lock failed on decrement for %s", self.id)
                raise RuntimeError("Concurrent update error")
            self.refresh_from_db()
        else:
            # atomically mark deleted + bump version
            updated = File.objects.filter(pk=self.pk, version=self.version).update(
                is_deleted=True,
                version=F("version") + 1,
            )
            if not updated:
                logger.error("Optimistic lock failed on delete for %s", self.id)
                raise RuntimeError("Concurrent update error")
            self.refresh_from_db()

    def delete_file_from_storage(self):
        """
        Physically remove the file from storage.
        Call this from your cleanup task, not here.
        """
        if self.file and default_storage.exists(self.file.name):
            default_storage.delete(self.file.name)
