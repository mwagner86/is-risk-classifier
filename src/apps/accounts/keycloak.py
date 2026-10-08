"""Look up the demo accounts in Keycloak, for the demo data only (``manage.py seed_demo``).

The app links a user to Keycloak by ``sub``, and Keycloak assigns that ID at random when it
imports the realm. Users for the demo data must therefore carry the real IDs, read here through
the admin API; otherwise their first login would collide with the pre-created username. The
users are created through the same role mapping as a login, never by a second sign-in path.
"""

import json
import os
from collections.abc import Iterable
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from apps.accounts.models import User
from apps.accounts.oidc import RoleMappingOIDCBackend

TIMEOUT = 10


class AccountError(Exception):
    """A demo account is missing in Keycloak or cannot be linked to a local user."""


def _call(url: str, *, token: str | None = None, form: dict[str, str] | None = None) -> Any:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = urlencode(form).encode() if form is not None else None
    # Fixed, configured base URL (OIDC_INTERNAL_BASE_URL), no user input
    request = Request(url, data=data, headers=headers)  # noqa: S310
    with urlopen(request, timeout=TIMEOUT) as response:  # noqa: S310
        return json.load(response)


def _admin_token(origin: str) -> str:
    password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "")
    if not password:
        raise ImproperlyConfigured("KEYCLOAK_ADMIN_PASSWORD is not set (see .env)")
    answer = _call(
        f"{origin}/realms/master/protocol/openid-connect/token",
        form={
            "grant_type": "password",
            "client_id": "admin-cli",
            "username": os.environ.get("KEYCLOAK_ADMIN_USERNAME", "admin"),
            "password": password,
        },
    )
    token: str = answer["access_token"]
    return token


def fetch_claims(usernames: Iterable[str]) -> list[dict[str, Any]]:
    """Read the accounts from the Keycloak admin API, shaped like the claims of a login."""
    origin = settings.OIDC_INTERNAL_ORIGIN
    realm = f"{origin}/admin/realms/{quote(settings.OIDC_REALM)}"
    token = _admin_token(origin)
    claims = []
    for username in usernames:
        query = urlencode({"username": username, "exact": "true"})
        found = _call(f"{realm}/users?{query}", token=token)
        if len(found) != 1:
            raise AccountError(f"Keycloak has no account {username!r} in {settings.OIDC_REALM}")
        account = found[0]
        groups = _call(f"{realm}/users/{quote(account['id'])}/groups", token=token)
        claims.append(
            {
                "sub": account["id"],
                "preferred_username": account["username"],
                "email": account.get("email", ""),
                "given_name": account.get("firstName", ""),
                "family_name": account.get("lastName", ""),
                "groups": [group["path"] for group in groups],
            }
        )
    return claims


def sync_users(claims: Iterable[dict[str, Any]]) -> dict[str, User]:
    """Create or update the local users exactly as a login would, keyed by username."""
    backend = RoleMappingOIDCBackend()
    users = {}
    for claim in claims:
        username = claim["preferred_username"]
        if not backend.verify_claims(claim):
            raise AccountError(f"{username!r} has no unique role group in Keycloak")
        user = User.objects.filter(oidc_subject=claim["sub"]).first()
        if user is None:
            if User.objects.filter(username=username).exists():
                raise AccountError(
                    f"A local user {username!r} exists with another Keycloak ID; "
                    "make reset starts from scratch"
                )
            user = backend.create_user(claim)
        else:
            user = backend.update_user(user, claim)
        users[username] = user
    return users
