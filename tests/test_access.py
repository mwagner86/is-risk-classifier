"""M-05: rights are checked on the server per role; whatever is not allowed is denied."""

from collections.abc import Iterator
from typing import Any

import pytest
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.models import Role, User
from apps.accounts.oidc import RoleMappingOIDCBackend, role_from_claims
from apps.core.access import declared_access

pytestmark = pytest.mark.req("M-05")

PUBLIC_ROUTES = {
    "healthz",
    "login_failed",
    "oidc_authentication_init",
    "oidc_authentication_callback",
    "oidc_logout",
}


def _patterns(resolver: URLResolver) -> Iterator[URLPattern]:
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _patterns(entry)
        else:
            yield entry


def test_m_05_every_route_declares_its_access() -> None:
    undeclared = [p.name for p in _patterns(get_resolver()) if declared_access(p.callback) is None]
    assert undeclared == []


def test_m_05_only_the_allowlisted_routes_are_public() -> None:
    public = {p.name for p in _patterns(get_resolver()) if declared_access(p.callback) is True}
    assert public == PUBLIC_ROUTES


@pytest.mark.django_db
def test_m_05_anonymous_user_is_sent_to_login(client: Client) -> None:
    response = client.get("/")
    assert response.status_code == 302
    assert response["Location"].startswith("/oidc/authenticate/")


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(Role))
def test_m_05_every_role_reaches_the_dashboard(role: Role, client: Client, make_user) -> None:
    client.force_login(make_user(role))
    assert client.get("/").status_code == 200


@pytest.mark.django_db
@pytest.mark.urls("tests.urls_access")
@pytest.mark.parametrize("role", list(Role))
def test_m_05_view_without_declaration_is_denied(role: Role, client: Client, make_user) -> None:
    client.force_login(make_user(role))
    assert client.get("/undeclared/").status_code == 403


@pytest.mark.django_db
@pytest.mark.urls("tests.urls_access")
@pytest.mark.parametrize("role", [r for r in Role if r != Role.CISO])
def test_m_05_view_denies_other_roles(role: Role, client: Client, make_user) -> None:
    client.force_login(make_user(role))
    assert client.get("/ciso-only/").status_code == 403


@pytest.mark.django_db
@pytest.mark.urls("tests.urls_access")
def test_m_05_view_admits_declared_role(client: Client, make_user) -> None:
    client.force_login(make_user(Role.CISO))
    assert client.get("/ciso-only/").status_code == 200


@pytest.mark.django_db
def test_healthz_is_public(client: Client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.content == b"ok"


# --- role mapping from the identity provider ------------------------------------------------


def _claims(*groups: str, **extra: Any) -> dict[str, Any]:
    return {"sub": "sub-1", "preferred_username": "melder", "groups": list(groups), **extra}


@pytest.mark.parametrize(
    ("groups", "expected"),
    [
        (["NUTZER"], Role.NUTZER),
        (["/RISK_MANAGER"], Role.RISK_MANAGER),
        (["CISO", "irgendwas"], Role.CISO),
        ([], None),
        (["irgendwas"], None),
        (["NUTZER", "ADMIN"], None),  # ambiguous: denied rather than guessed
    ],
)
def test_m_05_role_requires_exactly_one_role_group(
    groups: list[str], expected: Role | None
) -> None:
    assert role_from_claims(_claims(*groups)) == expected


def test_m_05_login_without_role_is_rejected() -> None:
    backend = RoleMappingOIDCBackend()
    assert backend.verify_claims(_claims()) is False
    assert backend.verify_claims(_claims("NUTZER", "CISO")) is False
    assert backend.verify_claims(_claims("NUTZER")) is True


@pytest.mark.django_db
def test_m_05_role_follows_the_identity_provider_on_every_login() -> None:
    backend = RoleMappingOIDCBackend()
    user = backend.create_user(_claims("NUTZER", given_name="Mara", family_name="Melder"))
    assert user.role == Role.NUTZER
    assert not user.has_usable_password()

    backend.update_user(user, _claims("RISK_MANAGER"))
    user.refresh_from_db()
    assert user.role == Role.RISK_MANAGER
    assert User.objects.filter(oidc_subject="sub-1").count() == 1
