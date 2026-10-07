from django.urls import include, path
from mozilla_django_oidc.views import (
    OIDCAuthenticationCallbackView,
    OIDCAuthenticationRequestView,
    OIDCLogoutView,
)

from apps.core import views
from apps.core.access import public

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("healthz", views.healthz, name="healthz"),
    path("anmeldung-abgelehnt/", views.login_failed, name="login_failed"),
    path("", include("apps.risks.urls")),
    # OIDC endpoints have to be reachable without a session
    path(
        "oidc/authenticate/",
        public(OIDCAuthenticationRequestView.as_view()),
        name="oidc_authentication_init",
    ),
    path(
        "oidc/callback/",
        public(OIDCAuthenticationCallbackView.as_view()),
        name="oidc_authentication_callback",
    ),
    path("oidc/logout/", public(OIDCLogoutView.as_view()), name="oidc_logout"),
]
