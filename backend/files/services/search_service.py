# files/services/search_service.py

import logging
from files.models import File

logger = logging.getLogger("files.services.search_service")


class SearchService:
    """
    Database-only search service.
    Clients can call search() to get paginated results from the DB.
    """

    def search(self, params: dict) -> dict:
        logger.info("SearchService.search called with params: %s", params)

        # Only load the fields we need
        qs = File.objects.filter(is_deleted=False).only(
            "id", "original_filename", "file_type", "size", "uploaded_at", "ref_count"
        )

        # Filename partial match
        if params.get("filename"):
            qs = qs.filter(original_filename__icontains=params["filename"])
            logger.debug("Applied filename filter: %s", params["filename"])

        # Extension filter
        ext = params.get("file_extension")
        if ext:
            ext = ext.lower().strip()
            qs = qs.filter(original_filename__iendswith=f".{ext}")
            logger.debug("Applied file_extension filter: .%s", ext)

        # Size range
        min_s, max_s = params.get("min_size"), params.get("max_size")
        if min_s is not None:
            qs = qs.filter(size__gte=min_s)
            logger.debug("Applied min_size filter: >=%d", min_s)
        if max_s is not None:
            qs = qs.filter(size__lte=max_s)
            logger.debug("Applied max_size filter: <=%d", max_s)

        # Date range
        sd, ed = params.get("start_date"), params.get("end_date")
        if sd:
            qs = qs.filter(uploaded_at__date__gte=sd)
            logger.debug("Applied start_date filter: >=%s", sd)
        if ed:
            qs = qs.filter(uploaded_at__date__lte=ed)
            logger.debug("Applied end_date filter: <=%s", ed)

        total = qs.count()
        logger.info("Total matching files before pagination: %d", total)

        # Pagination
        page = params.get("page", 1)
        page_size = params.get("page_size", 20)
        offset = (page - 1) * page_size
        results = qs.order_by("-uploaded_at")[offset : offset + page_size]
        logger.info(
            "Paginating: page=%d page_size=%d offset=%d returned=%d",
            page,
            page_size,
            offset,
            len(results),
        )

        items = [
            {
                "id": f.id,
                "original_filename": f.original_filename,
                "file_type": f.file_type,
                "file_size": f.size,
                "uploaded_at": f.uploaded_at,
                "ref_count": f.ref_count,
            }
            for f in results
        ]

        response = {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
            "source": "database",
        }
        logger.debug(
            "SearchService.search returning pagination summary: %s",
            {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items_returned": len(items),
            },
        )
        return response