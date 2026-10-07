"""Read-only view of the audit log (M-06, M-07)."""

import uuid

from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_safe

from apps.accounts.models import Role
from apps.audit.models import AuditAction, AuditEntry
from apps.core.access import allow_roles

OVERSIGHT_ROLES = (Role.RISK_MANAGER, Role.CISO, Role.ADMIN)
PAGE_SIZE = 50

# Technical field names in the log, shown in German
FIELD_LABELS = {
    "status": "Status",
    "probability": "Eintrittswahrscheinlichkeit",
    "impact": "Schadensausmaß",
    "origin": "Ursprung",
    "category": "Kategorie",
    "confidentiality": "Vertraulichkeit",
    "integrity": "Integrität",
    "availability": "Verfügbarkeit",
    "assets": "Assets",
    "title": "Titel",
    "description": "Beschreibung",
    "incident_response": "Incident Response",
    "state": "Antragsstatus",
    "kind": "Antrag",
    "channel": "Kanal",
    "csv": "CSV",
    "pdf": "PDF",
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
