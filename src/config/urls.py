from django.urls import include, path
from django.views.i18n import set_language
from mozilla_django_oidc.views import OIDCAuthenticationCallbackView, OIDCLogoutView

from apps.accounts.views import LocalisedAuthenticationRequestView
from apps.core import views
from apps.core.access import public

urlpatterns = [
    path("healthz", views.healthz, name="healthz"),
    path("anmeldung-abgelehnt/", views.login_failed, name="login_failed"),
    path("", include("apps.risks.urls")),
    path("", include("apps.cmdb.urls")),
    path("", include("apps.exports.urls")),
    path("", include("apps.audit.urls")),
    # OIDC endpoints have to be reachable without a session
    path(
        "oidc/authenticate/",
        public(LocalisedAuthenticationRequestView.as_view()),
        name="oidc_authentication_init",
    ),
    path(
        "oidc/callback/",
        public(OIDCAuthenticationCallbackView.as_view()),
        name="oidc_authentication_callback",
    ),
    path("oidc/logout/", public(OIDCLogoutView.as_view()), name="oidc_logout"),
    # Language switch (POST, CSRF-protected); also on the login-failed page, hence public
    path("sprache/", public(set_language), name="set_language"),
]
