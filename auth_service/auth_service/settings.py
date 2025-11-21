from pathlib import Path
import os
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

def env_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("true", "1", "yes", "on")

SECRET_KEY = config("SECRET_KEY")

DEBUG = env_bool(os.getenv("DEBUG"), default=False)

ALLOWED_HOSTS = config(
    "ALLOWED_HOSTS", 
    default="localhost,127.0.0.1"
).replace(" ", "").split(",")


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_yasg",
    "auth_app",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "auth_service.middleware.rate_limiting.RateLimitMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "auth_service.middleware.jwt_auth.JWTAuthenticationMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "auth_service.middleware.tenant_context.TenantContextMiddleware",
]


ROOT_URLCONF = "auth_service.urls"

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

WSGI_APPLICATION = "auth_service.wsgi.application"

SECURE_SSL_REDIRECT = env_bool(
    os.getenv("SECURE_SSL_REDIRECT"),
    default=(not DEBUG)
)

SESSION_COOKIE_SECURE = env_bool(
    os.getenv("SESSION_COOKIE_SECURE"),
    default=(not DEBUG)
)

CSRF_COOKIE_SECURE = env_bool(
    os.getenv("CSRF_COOKIE_SECURE"),
    default=(not DEBUG)
)

SESSION_COOKIE_HTTPONLY = env_bool(
    os.getenv("SESSION_COOKIE_HTTPONLY"),
    default=True
)

CSRF_COOKIE_HTTPONLY = env_bool(
    os.getenv("CSRF_COOKIE_HTTPONLY"),
    default=True
)

CSRF_TRUSTED_ORIGINS = config(
    "CSRF_TRUSTED_ORIGINS",
    default="http://localhost:3000,http://127.0.0.1:3000"
).replace(" ", "").split(",")

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("DB_NAME"),
        "USER": config("DB_USER"),
        "PASSWORD": config("DB_PASSWORD"),
        "HOST": config("DB_HOST"),
        "PORT": config("DB_PORT"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True


STATIC_URL = "/auth/static/"
STATIC_ROOT = os.path.join(BASE_DIR, "staticfiles")
STATICFILES_STORAGE = "whitenoise.storage.CompressedStaticFilesStorage"

LOG_LEVEL = "DEBUG" if DEBUG else "INFO"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
}

FORCE_SCRIPT_NAME = config("BASE_ROUTE", default=None)

JWT_PRIVATE_KEY_PATH = config("JWT_PRIVATE_KEY_PATH")
JWT_PUBLIC_KEY_PATH = config("JWT_PUBLIC_KEY_PATH")
JWT_ISSUER = config("JWT_ISSUER")
JWT_ALGORITHM = config("JWT_ALGORITHM")

REDIS_HOST = config("REDIS_HOST", default="localhost")
REDIS_PORT = int(config("REDIS_PORT", default=6379))
REDIS_DB = int(config("REDIS_DB", default=0))
REDIS_CHANNEL = config("REDIS_CHANNEL", default="user_created")
REDIS_STREAM_USERS = config("REDIS_STREAM_USERS", default="journies:stream:users")

REST_FRAMEWORK = {
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
    ],
}

SWAGGER_SETTINGS = {
    "SECURITY_DEFINITIONS": {"Bearer": {"type": "apiKey", "name": "Authorization", "in": "header"}},
    "USE_SESSION_AUTH": False,
    "SUPPORTED_SUBMIT_METHODS": ["get", "post", "put", "delete", "patch"],
    "DOC_EXPANSION": "none",
    "SHOW_EXTENSIONS": True,
    "SHOW_COMMON_EXTENSIONS": True,
}

AUTH_USER_MODEL = "auth_app.UserModel"

EMAIL_BACKEND = config(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.filebased.EmailBackend"
)

EMAIL_FILE_PATH = config(
    "EMAIL_FILE_PATH",
    default=os.path.join(BASE_DIR, "email_files")
)

EMAIL_HOST = config("EMAIL_HOST", default="smtp.gmail.com")
EMAIL_PORT = int(config("EMAIL_PORT", default=587))

EMAIL_USE_TLS = env_bool(os.getenv("EMAIL_USE_TLS"), default=True)

EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")

DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@example.com")

FRONTEND_URL = config("FRONTEND_URL", default="http://localhost:3000")
COMPASS_SERVICE_URL = config("COMPASS_SERVICE_URL", default="http://localhost:3001")

PASSWORD_CRYPT_KEY = config("PASSWORD_CRYPT_KEY")
SALT = config("SALT")