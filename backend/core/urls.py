from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions

# Swagger/OpenAPI setup
schema_view = get_schema_view(
    openapi.Info(
        title="File Hub API",
        default_version="v1",
        description="""
API for managing and storing files with deduplication.

## Features
- File upload with automatic deduplication
- File search and filtering
- Storage optimization through deduplication
- File metadata management

## Authentication
No authentication required for API access.
        """,
        contact=openapi.Contact(email="support@filehub.com"),
        license=openapi.License(name="MIT License"),
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
)

urlpatterns = [
    # Prometheus metrics
    path("", include("django_prometheus.urls")),
    # Main API routes (files app)
    path("api/", include("files.urls")),
    # Swagger UI
    path("", RedirectView.as_view(url="/swagger/", permanent=False)),
    path(
        "swagger/",
        schema_view.with_ui("swagger", cache_timeout=0),
        name="schema-swagger-ui",
    ),
    path(
        "redoc/",
        schema_view.with_ui("redoc", cache_timeout=0),
        name="schema-redoc",
    ),
    # Health check
    path(
        "health/",
        (
            include("health.urls")
            if "health" in settings.INSTALLED_APPS
            else RedirectView.as_view(url="/", permanent=False)
        ),
    ),
]

# Serve media in debug; in production, let your web server handle it
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
