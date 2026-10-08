"""Settings for the IS-Risk Classifier. All secrets come from the environment (.env)."""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent


def env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise ImproperlyConfigured(f"Environment variable {name} is required")
    return value


def env_list(name: str) -> list[str]:
    return [item.strip() for item in env(name, "").split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG", "false").lower() == "true"
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")

# django.contrib.admin is deliberately absent: its delete actions would break INV-03.
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "apps.core",
    "apps.accounts",
    "apps.audit",
    "apps.cmdb",
    "apps.risks",
    "apps.notifications",
    "apps.exports",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.core.security.SecurityHeadersMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.core.access.DenyByDefaultMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.navigation.navigation",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB"),
        # The application runs as the restricted role (setup_db_roles); migrations and tests use
        # the owner, i.e. POSTGRES_USER, when DATABASE_USER is not set
        "USER": env("DATABASE_USER", env("POSTGRES_USER")),
        "PASSWORD": env("DATABASE_PASSWORD", env("POSTGRES_PASSWORD")),
        "HOST": env("DATABASE_HOST", "db"),
        "PORT": env("DATABASE_PORT", "5432"),
    }
}

# Restricted role of the application (INV-03, M-06): created by `manage.py setup_db_roles`
DB_APP_ROLE = env("POSTGRES_APP_USER", "isrisk_app")
DB_APP_PASSWORD = env("POSTGRES_APP_PASSWORD", "")

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"

# Only the identity provider authenticates; there is no local password login.
AUTHENTICATION_BACKENDS = ["apps.accounts.oidc.RoleMappingOIDCBackend"]
AUTH_PASSWORD_VALIDATORS: list[dict[str, str]] = []

LOGIN_URL = "oidc_authentication_init"
LOGIN_REDIRECT_URL = "/"
LOGIN_REDIRECT_URL_FAILURE = "/anmeldung-abgelehnt/"
LOGOUT_REDIRECT_URL = "/"

# OpenID Connect (Keycloak). The browser uses the public URL, the server the internal one.
OIDC_REALM = env("OIDC_REALM", "is-risk")
OIDC_PUBLIC_ORIGIN = env("OIDC_PUBLIC_BASE_URL", "http://localhost:8080").rstrip("/")
OIDC_INTERNAL_ORIGIN = env("OIDC_INTERNAL_BASE_URL", "http://keycloak:8080").rstrip("/")
_oidc_public = f"{OIDC_PUBLIC_ORIGIN}/realms/{OIDC_REALM}"
_oidc_internal = f"{OIDC_INTERNAL_ORIGIN}/realms/{OIDC_REALM}"
OIDC_RP_CLIENT_ID = env("OIDC_RP_CLIENT_ID", "is-risk-classifier")
OIDC_RP_CLIENT_SECRET = env("OIDC_RP_CLIENT_SECRET")
OIDC_RP_SIGN_ALGO = "RS256"
OIDC_RP_SCOPES = "openid email profile"
OIDC_USE_PKCE = True
OIDC_OP_AUTHORIZATION_ENDPOINT = f"{_oidc_public}/protocol/openid-connect/auth"
OIDC_OP_LOGOUT_ENDPOINT = f"{_oidc_public}/protocol/openid-connect/logout"
OIDC_OP_TOKEN_ENDPOINT = f"{_oidc_internal}/protocol/openid-connect/token"
OIDC_OP_USER_ENDPOINT = f"{_oidc_internal}/protocol/openid-connect/userinfo"
OIDC_OP_JWKS_ENDPOINT = f"{_oidc_internal}/protocol/openid-connect/certs"
OIDC_STORE_ID_TOKEN = True
OIDC_OP_LOGOUT_URL_METHOD = "apps.accounts.oidc.provider_logout_url"

# --- Hardening (M-05) ---------------------------------------------------------------------

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 60 * 60  # one working day
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = True  # htmx takes the token from the page, not from the cookie
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

# Behind a TLS-terminating proxy. Local development runs on plain http and leaves this off.
HTTPS = env("DJANGO_HTTPS", "false").lower() == "true"
if HTTPS:
    LANGUAGE_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 365 * 24 * 60 * 60
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# German is the source language and the default; English comes from locale/en. The choice is
# kept in a cookie (language switch in the header); without it the browser's language decides.
LANGUAGE_CODE = "de"
LANGUAGES = [("de", "Deutsch"), ("en", "English")]
LOCALE_PATHS = [BASE_DIR / "locale"]
FORMAT_MODULE_PATH = ["config.formats"]
LANGUAGE_COOKIE_NAME = "language"
LANGUAGE_COOKIE_AGE = 365 * 24 * 60 * 60
LANGUAGE_COOKIE_SAMESITE = "Lax"
LANGUAGE_COOKIE_HTTPONLY = True
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# The runtime image collects static files with hashed names; development serves them directly
if env("STATIC_MANIFEST", "false").lower() == "true":
    # Serve the collected files from the app server; behind the security headers middleware
    MIDDLEWARE.insert(
        MIDDLEWARE.index("apps.core.security.SecurityHeadersMiddleware") + 1,
        "whitenoise.middleware.WhiteNoiseMiddleware",
    )
    STORAGES = {
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    }

# No inline script or style anywhere (tests/test_hardening.py); the logout form redirects to the
# identity provider, hence its origin in form-action
CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self'",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        f"form-action 'self' {OIDC_PUBLIC_ORIGIN}",
    ]
)
PERMISSIONS_POLICY = "camera=(), microphone=(), geolocation=(), payment=(), usb=()"

# Links in notifications point here; they lead to the risk only after login (M-09)
APP_BASE_URL = env("APP_BASE_URL", "http://localhost:8000")

# Escalation (US-03) and hand-over to IT operations (AK-01.2)
IR_TEAM_EMAILS = env_list("IR_TEAM_EMAILS")
IR_TEAM_PHONES = env_list("IR_TEAM_PHONES")
IT_OPS_EMAIL = env("IT_OPS_EMAIL", "")
NOTIFICATION_GATEWAY = env("NOTIFICATION_GATEWAY", "apps.notifications.gateway.MockGateway")
# Mock only: ok, timeout or 5xx — forces the gateway failure of AK-03.3
NOTIFY_MOCK_MODE = env("NOTIFY_MOCK_MODE", "ok")
# HttpGateway: the notify-gateway service (the worker sets NOTIFICATION_GATEWAY in compose)
NOTIFY_GATEWAY_URL = env("NOTIFY_GATEWAY_URL", "http://notify-gateway:8002/messages")
NOTIFY_GATEWAY_TOKEN = env("NOTIFY_GATEWAY_TOKEN", "")
NOTIFY_GATEWAY_TIMEOUT = float(env("NOTIFY_GATEWAY_TIMEOUT", "5"))

# PDF export: rendered by the separate pdf-renderer service without database access (M-03)
PDF_RENDERER_URL = env("PDF_RENDERER_URL", "http://pdf-renderer:8001/render")
PDF_RENDERER_TIMEOUT = int(env("PDF_RENDERER_TIMEOUT", "30"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
