# files/apps.py

import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)


class FilesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "files"

    def ready(self):
        # Ensure models are registered
        import files.models  # noqa: F401
