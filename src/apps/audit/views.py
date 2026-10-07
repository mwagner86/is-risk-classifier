"""Read-only view of the audit log (M-06, M-07)."""

import uuid
from typing import TYPE_CHECKING

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_safe

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEntry
from apps.core.access import allow_roles

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise
else:
    StrOrPromise = str

OVERSIGHT_ROLES = (Role.RISK_MANAGER, Role.CISO, Role.ADMIN)
PAGE_SIZE = 50

# Technical field names in the log, shown in German
FIELD_LABELS: dict[str, StrOrPromise] = {
    "status": _("Status"),
    "probability": _("Eintrittswahrscheinlichkeit"),
    "impact": _("Schadensausmaß"),
    "origin": _("Ursprung"),
    "category": _("Kategorie"),
    "confidentiality": _("Vertraulichkeit"),
    "integrity": _("Integrität"),
    "availability": _("Verfügbarkeit"),
    "assets": _("Assets"),
    "title": _("Titel"),
    "description": _("Beschreibung"),
    "incident_response": _("Incident Response"),
    "state": _("Antragsstatus"),
    "kind": _("Antrag"),
    "channel": _("Kanal"),
    "csv": _("CSV"),
    "pdf": _("PDF"),
}


@allow_roles(*OVERSIGHT_ROLES)
@require_safe
def audit_log(request: HttpRequest) -> HttpResponse:
    entries = AuditEntry.objects.select_related("actor", "risk").order_by("-created_at")
    action = request.GET.get("action", "")
    if action in AuditAction.values:
        entries = entries.filter(action=action)
    else:
        action = ""
    risk = request.GET.get("risk", "")
    try:
        entries = entries.filter(risk_id=uuid.UUID(risk)) if risk else entries
    except ValueError:
        risk = ""
    page = Paginator(entries, PAGE_SIZE).get_page(request.GET.get("seite"))
    context = {
        "page": page,
        "actions": AuditAction.choices,
        "action": action,
        "risk": risk,
        "field_labels": FIELD_LABELS,
    }
    return render(request, "audit/log.html", context)
