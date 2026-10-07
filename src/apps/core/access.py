"""Deny-by-default authorisation (M-05).

Every view must declare who may call it: ``@allow_roles(...)`` for signed-in roles or
``@public`` for the few endpoints that work without a session. A view without a declaration is
rejected with 403, so forgetting the check fails closed instead of open.
"""

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.contrib.auth.views import redirect_to_login
from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.utils.translation import gettext

from apps.accounts.models import Role

ALLOWED_ROLES_ATTR = "allowed_roles"
PUBLIC_ATTR = "is_public"


def allow_roles[View: Callable[..., Any]](*roles: Role) -> Callable[[View], View]:
    if not roles:
        raise ValueError("allow_roles needs at least one role")

    def decorator(view: View) -> View:
        setattr(view, ALLOWED_ROLES_ATTR, frozenset(roles))
        return view

    return decorator


def public[View: Callable[..., Any]](view: View) -> View:
    setattr(view, PUBLIC_ATTR, True)
    return view


def declared_access(view: Callable[..., Any]) -> bool | frozenset[Role] | None:
    """Return True for public views, the role set for protected ones, None if undeclared."""
    if getattr(view, PUBLIC_ATTR, False):
        return True
    roles: frozenset[Role] | None = getattr(view, ALLOWED_ROLES_ATTR, None)
    return roles


class DenyByDefaultMiddleware:
    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        return self.get_response(request)

    def process_view(
        self,
        request: HttpRequest,
        view_func: Callable[..., Any],
        view_args: tuple[Any, ...],
        view_kwargs: dict[str, Any],
    ) -> HttpResponse | None:
        access = declared_access(view_func)
        if access is True:
            return None
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), settings.LOGIN_URL)
        if not access or getattr(request.user, "role", None) not in access:
            return HttpResponseForbidden(gettext("Zugriff verweigert."))
        return None
