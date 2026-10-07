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
    "django.contrib.sessions.middleware.SessionMiddleware",
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
        "USER": env("POSTGRES_USER"),
        "PASSWORD": env("POSTGRES_PASSWORD"),
        "HOST": env("DATABASE_HOST", "db"),
        "PORT": env("DATABASE_PORT", "5432"),
    }
}

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
_oidc_public = f"{env('OIDC_PUBLIC_BASE_URL', 'http://localhost:8080')}/realms/{OIDC_REALM}"
_oidc_internal = f"{env('OIDC_INTERNAL_BASE_URL', 'http://keycloak:8080')}/realms/{OIDC_REALM}"
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

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

LANGUAGE_CODE = "de-de"
TIME_ZONE = "Europe/Berlin"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]

# Links in notifications point here; they lead to the risk only after login (M-09)
APP_BASE_URL = env("APP_BASE_URL", "http://localhost:8000")

# Escalation (US-03) and hand-over to IT operations (AK-01.2)
IR_TEAM_EMAILS = env_list("IR_TEAM_EMAILS")
IR_TEAM_PHONES = env_list("IR_TEAM_PHONES")
IT_OPS_EMAIL = env("IT_OPS_EMAIL", "")
NOTIFICATION_GATEWAY = env("NOTIFICATION_GATEWAY", "apps.notifications.gateway.MockGateway")
# Mock only: ok, timeout or 5xx — forces the gateway failure of AK-03.3
NOTIFY_MOCK_MODE = env("NOTIFY_MOCK_MODE", "ok")

# PDF export: rendered by the separate pdf-renderer service without database access (M-03)
PDF_RENDERER_URL = env("PDF_RENDERER_URL", "http://pdf-renderer:8001/render")
PDF_RENDERER_TIMEOUT = int(env("PDF_RENDERER_TIMEOUT", "30"))

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}
