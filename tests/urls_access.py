"""URLconf for the deny-by-default tests: one undeclared view, one CISO-only view."""

from django.http import HttpRequest, HttpResponse
from django.urls import path

from apps.accounts.models import Role
from apps.core.access import allow_roles


def undeclared(request: HttpRequest) -> HttpResponse:
    return HttpResponse("should never be reachable")


@allow_roles(Role.CISO)
def ciso_only(request: HttpRequest) -> HttpResponse:
    return HttpResponse("ok")


urlpatterns = [
    path("undeclared/", undeclared),
    path("ciso-only/", ciso_only),
]
