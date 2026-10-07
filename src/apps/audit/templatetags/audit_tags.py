"""Display helpers for audit entries. The log stores raw values as evidence; the page shows them
with their German labels."""

from typing import Any

from django import template
from django.utils.translation import gettext

from apps.risks.models import ApprovalKind, ApprovalState, Origin, RiskCategory, RiskStatus

register = template.Library()

VALUE_LABELS: dict[str, dict[str, Any]] = {
    "status": dict(RiskStatus.choices),
    "category": dict(RiskCategory.choices),
    "origin": dict(Origin.choices),
    "state": dict(ApprovalState.choices),
    "kind": dict(ApprovalKind.choices),
}
BOOLEAN_FIELDS = {"confidentiality", "integrity", "availability"}


@register.filter
def lookup(mapping: dict[str, Any], key: str) -> str:
    return str(mapping.get(key, key))


@register.simple_tag
def audit_value(field: str, value: str) -> str:
    if field in BOOLEAN_FIELDS:
        return {"True": gettext("ja"), "False": gettext("nein")}.get(value, value)
    return str(VALUE_LABELS.get(field, {}).get(value, value))
