"""
Django settings for paolapsicope_backend project.
"""

from pathlib import Path
import os
import dj_database_url
from dotenv import load_dotenv
from datetime import timedelta
from urllib.parse import urlparse

env_path = Path(__file__).resolve().parent.parent / ".env"
if env_path.exists():
    load_dotenv(dotenv_path=env_path, override=True, encoding="utf-8")

BASE_DIR = Path(__file__).resolve().parent.parent


def url_with_default_scheme(value):
    cleaned = str(value or "").strip().strip('"').strip("'").rstrip("/")
    if not cleaned:
        return ""

    parsed = urlparse(cleaned)
    if parsed.scheme and parsed.netloc:
        return cleaned

    if cleaned.startswith(("localhost", "127.0.0.1", "[::1]")):
        return f"http://{cleaned}"

    return f"https://{cleaned}"


def public_frontend_url(value, default="http://localhost:3000"):
    raw_value = str(value or default or "")
    candidates = [
        url_with_default_scheme(part)
        for part in raw_value.replace("\n", ",").replace(";", ",").split(",")
        if part.strip()
    ]
    candidates = [candidate for candidate in candidates if candidate]
    if not candidates:
        return url_with_default_scheme(default)

    custom_domain = [
        candidate
        for candidate in candidates
        if "up.railway.app" not in urlparse(candidate).netloc
    ]
    return (custom_domain[0] if custom_domain else candidates[0]).rstrip("/")

SECRET_KEY = os.environ.get("SECRET_KEY", "django-insecure-cambia-en-produccion")

DEBUG = os.environ.get("DEBUG", "False").lower() == "true"

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "*").split(",")

AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", str(not DEBUG)).lower() == "true"
AUTH_COOKIE_SAMESITE = os.environ.get(
    "AUTH_COOKIE_SAMESITE",
    "Lax" if DEBUG else "None",
)

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "PaolazabalaPsicope@gmail.com")
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH", "")
ADMIN_JWT_SECRET = os.environ.get("ADMIN_JWT_SECRET", SECRET_KEY)
ADMIN_TOKEN_TTL = int(os.environ.get("ADMIN_TOKEN_TTL", "86400"))
ALLOW_BUILTIN_ADMIN_FALLBACK = (
    os.environ.get("ALLOW_BUILTIN_ADMIN_FALLBACK", "False").lower() == "true"
)

CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "")
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "")
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "")
CLOUDINARY_SETTINGS_SECRET = os.environ.get("CLOUDINARY_SETTINGS_SECRET", SECRET_KEY)
CLOUDINARY_UPLOAD_FOLDER = os.environ.get("CLOUDINARY_UPLOAD_FOLDER", "paola-psicope/products")
CLOUDINARY_MAX_UPLOAD_BYTES = int(os.environ.get("CLOUDINARY_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
CLOUDINARY_DOWNLOAD_FOLDER = os.environ.get("CLOUDINARY_DOWNLOAD_FOLDER", "paola-psicope/downloads")
CLOUDINARY_MAX_DOWNLOAD_BYTES = int(os.environ.get("CLOUDINARY_MAX_DOWNLOAD_BYTES", str(25 * 1024 * 1024)))
CLOUDINARY_AVATAR_FOLDER = os.environ.get("CLOUDINARY_AVATAR_FOLDER", "paola-psicope/avatars")
CLOUDINARY_AVATAR_MAX_BYTES = int(os.environ.get("CLOUDINARY_AVATAR_MAX_BYTES", str(5 * 1024 * 1024)))

DATA_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("DATA_UPLOAD_MAX_MEMORY_SIZE", str(120 * 1024 * 1024)))
FILE_UPLOAD_MAX_MEMORY_SIZE = int(os.environ.get("FILE_UPLOAD_MAX_MEMORY_SIZE", str(120 * 1024 * 1024)))

R2_ACCOUNT_ID = os.environ.get("R2_ACCOUNT_ID", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET_NAME = os.environ.get("R2_BUCKET_NAME", "")
R2_PUBLIC_BASE_URL = os.environ.get("R2_PUBLIC_BASE_URL", "")
R2_DOWNLOAD_PREFIX = os.environ.get("R2_DOWNLOAD_PREFIX", "paola-psicope/products/downloads")
DOWNLOAD_MAX_BYTES = int(os.environ.get("DOWNLOAD_MAX_BYTES", str(100 * 1024 * 1024)))

NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
NVIDIA_SETTINGS_SECRET = os.environ.get("NVIDIA_SETTINGS_SECRET", SECRET_KEY)
NVIDIA_BASE_URL = url_with_default_scheme(
    os.environ.get("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
)
NVIDIA_MODEL = os.environ.get("NVIDIA_MODEL", "")
NVIDIA_IMAGE_MODEL = os.environ.get("NVIDIA_IMAGE_MODEL", "")
NVIDIA_WORKBOOK_PLAN_MODEL = os.environ.get("NVIDIA_WORKBOOK_PLAN_MODEL", NVIDIA_MODEL)
NVIDIA_WORKBOOK_BUILD_MODEL = os.environ.get("NVIDIA_WORKBOOK_BUILD_MODEL", NVIDIA_MODEL)
NVIDIA_WORKBOOK_SKILL = os.environ.get(
    "NVIDIA_WORKBOOK_SKILL",
    (
        "Sos Paola Psicope en modo creadora de cuadernillos. "
        "Transforma pedidos libres en planes psicopedagogicos A4, claros, imprimibles, "
        "con actividades verificables y recursos visuales sin texto dentro de imagenes."
    ),
)

BACKEND_PUBLIC_URL = url_with_default_scheme(os.environ.get("BACKEND_PUBLIC_URL", ""))
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
RESEND_FROM_EMAIL = os.environ.get("RESEND_FROM_EMAIL", "Paola Psicopé <onboarding@resend.dev>")
RESEND_REPLY_TO = os.environ.get("RESEND_REPLY_TO", "")
RESEND_TIMEOUT_SECONDS = int(os.environ.get("RESEND_TIMEOUT_SECONDS", "15"))
EMAIL_VERIFICATION_TOKEN_TTL_SECONDS = int(
    os.environ.get("EMAIL_VERIFICATION_TOKEN_TTL_SECONDS", str(60 * 60 * 24))
)
EMAIL_VERIFICATION_CODE_TTL_SECONDS = int(
    os.environ.get("EMAIL_VERIFICATION_CODE_TTL_SECONDS", str(10 * 60))
)
EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS = int(
    os.environ.get("EMAIL_VERIFICATION_CODE_MAX_ATTEMPTS", "5")
)
PASSWORD_RESET_CODE_TTL_SECONDS = int(
    os.environ.get("PASSWORD_RESET_CODE_TTL_SECONDS", str(10 * 60))
)
PASSWORD_RESET_CODE_MAX_ATTEMPTS = int(
    os.environ.get("PASSWORD_RESET_CODE_MAX_ATTEMPTS", "5")
)
EMAIL_VERIFICATION_SUCCESS_URL = url_with_default_scheme(os.environ.get("EMAIL_VERIFICATION_SUCCESS_URL", ""))
EMAIL_VERIFICATION_ERROR_URL = url_with_default_scheme(os.environ.get("EMAIL_VERIFICATION_ERROR_URL", ""))
MP_ACCESS_TOKEN = os.environ.get("MP_ACCESS_TOKEN", "")
MP_WEBHOOK_SECRET = os.environ.get("MP_WEBHOOK_SECRET", "")
MP_MODE = os.environ.get("MP_MODE", "auto").strip().lower()
MP_ALLOW_UNSIGNED_WEBHOOKS_IN_DEBUG = (
    os.environ.get("MP_ALLOW_UNSIGNED_WEBHOOKS_IN_DEBUG", "False").lower() == "true"
)
FRONTEND_URL = public_frontend_url(os.environ.get("FRONTEND_URL", "http://localhost:3000"))
EMAIL_ASSETS_BASE_URL = os.environ.get("EMAIL_ASSETS_BASE_URL", "").rstrip("/")

GITHUB_OWNER = os.environ.get("GITHUB_OWNER", "negro123454332-jpg").strip()
GITHUB_REPO = os.environ.get("GITHUB_REPO", "app-pao").strip()
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_APK_ASSET_NAME = os.environ.get("GITHUB_APK_ASSET_NAME", "paola-psicope.apk").strip()
GITHUB_SHA256_ASSET_NAME = os.environ.get(
    "GITHUB_SHA256_ASSET_NAME", "paola-psicope.apk.sha256"
).strip()
GITHUB_RELEASE_CACHE_TTL_SECONDS = int(os.environ.get("GITHUB_RELEASE_CACHE_TTL_SECONDS", "300"))
GITHUB_CONNECT_TIMEOUT_SECONDS = int(os.environ.get("GITHUB_CONNECT_TIMEOUT_SECONDS", "5"))
GITHUB_READ_TIMEOUT_SECONDS = int(os.environ.get("GITHUB_READ_TIMEOUT_SECONDS", "30"))

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework_simplejwt",
    "corsheaders",
    "api",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "paolapsicope_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "paolapsicope_backend.wsgi.application"

DATABASES = {
    "default": dj_database_url.config(
        default=os.environ.get("DATABASE_URL", "sqlite:///db.sqlite3"),
        conn_max_age=600,
    )
}

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

LANGUAGE_CODE = "es-ar"
TIME_ZONE = "America/Argentina/Buenos_Aires"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

AUTH_USER_MODEL = "api.User"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "api.authentication.JWTCookieAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.AllowAny",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "10080"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": False,
    "BLACKLIST_AFTER_ROTATION": False,
    "ALGORITHM": "HS256",
    "SIGNING_KEY": os.environ.get("SECRET_KEY", "django-insecure-cambia-en-produccion"),
    "AUTH_HEADER_TYPES": ("Bearer",),
}

DEFAULT_CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://paola-psicope.vercel.app",
    "https://workenginecorp.com.ar",
    "https://www.workenginecorp.com.ar",
]
CONFIGURED_CORS_ALLOWED_ORIGINS = [
    url_with_default_scheme(origin)
    for origin in os.environ.get("CORS_ALLOWED_ORIGINS", "").split(",")
    if origin.strip()
]

CORS_ALLOWED_ORIGINS = list(
    dict.fromkeys([*DEFAULT_CORS_ALLOWED_ORIGINS, *CONFIGURED_CORS_ALLOWED_ORIGINS])
)

CORS_ALLOW_CREDENTIALS = True

CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_HTTPONLY = True

SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    USE_X_FORWARDED_HOST = True
    SECURE_SSL_REDIRECT = os.environ.get("SECURE_SSL_REDIRECT", "True").lower() == "true"
    SESSION_COOKIE_SECURE = AUTH_COOKIE_SECURE
    CSRF_COOKIE_SECURE = AUTH_COOKIE_SECURE
