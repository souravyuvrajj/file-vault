import os
from pathlib import Path
from dotenv import load_dotenv

# ─── Base ───────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # ensure .env is loaded

# ─── Core Django Settings ──────────────────────────────────────────────────────
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = os.getenv("DJANGO_DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [h.strip() for h in os.environ["DJANGO_ALLOWED_HOSTS"].split(",")]


# ─── Applications & Middleware ────────────────────────────────────────────────

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "corsheaders",
    "drf_yasg",
    "django_prometheus",
    "django_filters",
    # Your apps
    "files",
]

MIDDLEWARE = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

ROOT_URLCONF = "core.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "core.wsgi.application"

# ─── Database ──────────────────────────────────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": os.environ["DB_ENGINE"],
        "NAME": os.getenv("DB_NAME", BASE_DIR / "data" / "db.sqlite3"),
    }
}


# ─── Static & Media ───────────────────────────────────────────────────────────

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ─── Internationalization ──────────────────────────────────────────────────────

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
# (USE_I18N, USE_TZ, DEFAULT_AUTO_FIELD all use Django defaults)

# ─── File Upload Settings ───────────────────────────────────────────────────────
MAX_UPLOAD_SIZE = int(os.environ["MAX_UPLOAD_SIZE"])
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_SIZE
MAX_FILENAME_LENGTH = int(os.environ["MAX_FILENAME_LENGTH"])

# MIME types & extensions directly from .env
ALLOWED_FILE_TYPES = [t.strip() for t in os.environ["ALLOWED_FILE_TYPES"].split(",")]
ALLOWED_FILE_EXTENSIONS = [e.strip().lower() for e in os.environ["ALLOWED_FILE_EXTENSIONS"].split(",")]

# ─── REST Framework ────────────────────────────────────────────────────────────
REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
        "rest_framework.parsers.MultiPartParser",
        "rest_framework.parsers.FormParser",
    ],
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": int(os.environ["PAGE_SIZE"]),
}

# ─── CORS & CSRF ────────────────────────────────────────────────────────────────
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "False").lower() == "true"
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOWED_ORIGINS = [o.strip() for o in os.environ["DJANGO_CORS_ALLOWED_ORIGINS"].split(",")]
CSRF_TRUSTED_ORIGINS = CORS_ALLOWED_ORIGINS.copy()


# ─── Redis / Cache ─────────────────────────────────────────────────────────────
REDIS_HOST = os.environ["REDIS_HOST"]
REDIS_PORT = os.environ["REDIS_PORT"]
REDIS_DB = os.environ["REDIS_DB"]
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        "KEY_PREFIX": os.environ["CACHE_KEY_PREFIX"],
        "TIMEOUT": int(os.environ["CACHE_TIMEOUT"]),
    }
}
# ─── Logging ──────────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ["LOG_LEVEL"]
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler", "level": LOG_LEVEL},
        "file": {
            "class": "logging.FileHandler",
            "filename": BASE_DIR / "logs" / "debug.log",
            "level": LOG_LEVEL,
        },
    },
    "root": {"handlers": ["console", "file"], "level": LOG_LEVEL},
}

# ─── Swagger / OpenAPI ────────────────────────────────────────────────────────

SWAGGER_SETTINGS = {
    "USE_SESSION_AUTH": False,
    "APIS_SORTER": "alpha",
    "JSON_EDITOR": True,
    "OPERATIONS_SORTER": "alpha",
    "VALIDATOR_URL": None,
    "DEFAULT_AUTO_SCHEMA_CLASS": "drf_yasg.inspectors.SwaggerAutoSchema",
}
