import uuid
import hashlib
import logging
from typing import Any, Tuple, Dict

from django.db import transaction, IntegrityError
from django.db.models import F, Sum

from files.models import File
from files.exceptions import FileError, FileIntegrityError, FileMissingError

logger = logging.getLogger("files.services.file_service")


class FileManager:
    """
    Handles deduplicated uploads, deletes, storage-summary caching,
    and download lookup—no external tasks.
    """

    def __init__(self, hash_algorithm: str = "sha256"):
        self.hash_algorithm = hash_algorithm.lower()

    def _compute_hash(self, file_obj: Any, chunk_size: int = 4 << 20) -> str:
        start_pos = file_obj.tell()
        hasher = hashlib.md5() if self.hash_algorithm == "md5" else hashlib.sha256()
        try:
            file_obj.seek(0)
            for chunk in iter(lambda: file_obj.read(chunk_size), b""):
                hasher.update(chunk)
        finally:
            file_obj.seek(start_pos)
        return hasher.hexdigest()

    def upload_file(
        self,
        file_obj: Any,
        filename: str,
        file_type: str,
    ) -> Tuple[File, bool]:
        """
        - Compute content-hash
        - Create new File or increment ref_count on duplicate
        Returns: (File instance, is_new: bool)
        """
        file_hash = self._compute_hash(file_obj)
        size = file_obj.size
        logger.info("upload_file: %s (%d bytes) → hash=%s", filename, size, file_hash)

        existing_qs = File.objects.filter(file_hash=file_hash, is_deleted=False)
        if existing_qs.exists():
            existing = existing_qs.first()
            logger.debug(
                "Duplicate hash %s found (id=%s ref_count=%s)",
                file_hash, existing.id, existing.ref_count
            )

        try:
            with transaction.atomic():
                new_file = File(
                    id=uuid.uuid4(),
                    original_filename=filename,
                    file_type=file_type,
                    size=size,
                    file_hash=file_hash,
                    ref_count=1,
                )
                ext = filename.rsplit(".", 1)[-1].lower()
                storage_name = f"{file_hash}.{ext}"
                new_file.file.save(storage_name, file_obj, save=False)
                new_file.save()

            logger.info("Created new File id=%s (ref_count=1)", new_file.id)
            return new_file, True

        except IntegrityError as e:
            logger.warning("IntegrityError on upload; incrementing ref_count for hash %s", file_hash)
            try:
                existing = File.objects.get(file_hash=file_hash, is_deleted=False)
            except File.DoesNotExist:
                raise FileIntegrityError(f"Hash collision: {e}")

            try:
                existing.increment_ref_count()
                logger.info(
                    "Incremented ref_count for id=%s now %s",
                    existing.id, existing.ref_count
                )
            except RuntimeError as e_lock:
                logger.error("Optimistic lock failed on increment: %s", e_lock)
                raise FileError("Concurrent update error") from e_lock

            return existing, False

    def delete_file(self, file_id: Any) -> bool:
        """
        Decrement ref_count or mark deleted.
        Returns True if the file was soft-deleted.
        """
        logger.info("delete_file called for id=%s", file_id)

        with transaction.atomic():
            try:
                f = File.objects.get(pk=file_id, is_deleted=False)
            except File.DoesNotExist:
                raise FileMissingError(f"File not found: {file_id}")

            try:
                f.decrement_ref_count()
                deleted = f.is_deleted
                logger.info(
                    "After delete_file: id=%s deleted=%s (ref_count=%s)",
                    file_id, deleted, f.ref_count
                )
                return deleted
            except RuntimeError as e_lock:
                logger.error("Optimistic lock failed on delete: %s", e_lock)
                raise FileError("Concurrent update error") from e_lock

    def get_storage_summary(self) -> Dict[str, Any]:
        """
        Compute:
          - total_file_size = sum(size * ref_count)
          - deduplicated_storage = sum(size)
          - storage_saved = total - dedup
          - savings_percentage = (saved/total)*100
        """
        logger.info("Recomputing storage summary")
        stats = File.objects.filter(is_deleted=False).aggregate(
            total_uploaded=Sum(F("size") * F("ref_count")),
            dedup_storage=Sum("size"),
        )
        total = stats["total_uploaded"] or 0
        dedup = stats["dedup_storage"] or 0
        saved = total - dedup
        pct = round((saved / total * 100) if total else 0, 2)

        return {
            "total_file_size": total,
            "deduplicated_storage": dedup,
            "storage_saved": saved,
            "savings_percentage": pct,
        }

    def get_file(self, file_id: Any) -> File:
        """
        Fetch a non-deleted File instance.
        """
        try:
            f = File.objects.get(pk=file_id, is_deleted=False)
            logger.debug("get_file found id=%s", file_id)
            return f
        except File.DoesNotExist:
            logger.warning("get_file: File not found id=%s", file_id)
            raise FileMissingError(f"File not found: {file_id}")
