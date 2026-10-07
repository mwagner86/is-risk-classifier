"""Login via Keycloak: map exactly one group to a role, otherwise reject (M-05)."""

import logging
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.http import HttpRequest
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from apps.accounts.models import Role, User

logger = logging.getLogger(__name__)


def role_from_claims(claims: dict[str, Any]) -> Role | None:
    """Return the role if the ``groups`` claim names exactly one known role group."""
    groups = claims.get("groups") or []
    roles = {Role(name) for name in (group.lstrip("/") for group in groups) if name in Role.values}
    if len(roles) != 1:
        return None
    return roles.pop()


class RoleMappingOIDCBackend(OIDCAuthenticationBackend):  # type: ignore[misc]
    def verify_claims(self, claims: dict[str, Any]) -> bool:
        if not claims.get("sub") or not claims.get("preferred_username"):
            return False
        if role_from_claims(claims) is None:
            logger.warning(
                "login rejected: no unique role group for %s", claims.get("preferred_username")
            )
            return False
        return True

    def filter_users_by_claims(self, claims: dict[str, Any]) -> Any:
        return User.objects.filter(oidc_subject=claims["sub"])

    def create_user(self, claims: dict[str, Any]) -> User:
        user: User = User.objects.create_user(
            username=claims["preferred_username"],
            oidc_subject=claims["sub"],
            role=role_from_claims(claims),
        )
        return self.update_user(user, claims)

    def update_user(self, user: User, claims: dict[str, Any]) -> User:
        # The identity provider is the source of truth: re-sync role and profile on every login.
        role = role_from_claims(claims)
        assert role is not None  # noqa: S101 - verify_claims ran before
        user.username = claims["preferred_username"]
        user.email = claims.get("email", "")
        user.first_name = claims.get("given_name", "")
        user.last_name = claims.get("family_name", "")
        user.role = role
        # Only once: a fresh unusable hash on every login would change the session auth hash and
        # sign the user out everywhere else
        if user.has_usable_password():
            user.set_unusable_password()
        user.save()
        return user


def provider_logout_url(request: HttpRequest) -> str:
    """End the Keycloak session as well (RP-initiated logout)."""
    params = {
        "client_id": settings.OIDC_RP_CLIENT_ID,
        "post_logout_redirect_uri": request.build_absolute_uri(settings.LOGOUT_REDIRECT_URL),
    }
    id_token = request.session.get("oidc_id_token")
    if id_token:
        params["id_token_hint"] = id_token
    return f"{settings.OIDC_OP_LOGOUT_ENDPOINT}?{urlencode(params)}"
