"""Login request that hands the chosen language to Keycloak, so its pages match the app."""

from typing import Any

from django.http import HttpRequest
from django.utils.translation import get_language
from mozilla_django_oidc.views import OIDCAuthenticationRequestView


class LocalisedAuthenticationRequestView(OIDCAuthenticationRequestView):  # type: ignore[misc]
    def get_extra_params(self, request: HttpRequest) -> dict[str, Any]:
        params: dict[str, Any] = super().get_extra_params(request)
        params["ui_locales"] = get_language() or "de"
        return params
