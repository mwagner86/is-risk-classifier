from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from apps.accounts.models import Role
from apps.cmdb.models import Asset
from apps.core.access import allow_roles


@allow_roles(*Role)
@require_safe
def asset_list(request: HttpRequest) -> HttpResponse:
    """Read-only view of the CMDB mirror (decision 5)."""
    return render(request, "cmdb/list.html", {"assets": Asset.objects.order_by("cmdb_key")})
