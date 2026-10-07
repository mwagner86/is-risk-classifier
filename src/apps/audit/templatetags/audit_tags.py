"""Display helpers for audit entries. The log stores raw values as evidence; the page shows them
with their German labels."""

from django import template

from apps.risks.models import ApprovalKind, ApprovalState, Origin, RiskCategory, RiskStatus

register = template.Library()

VALUE_LABELS: dict[str, dict[str, str]] = {
    "status": dict(RiskStatus.choices),
    "category": dict(RiskCategory.choices),
    "origin": dict(Origin.choices),
    "state": dict(ApprovalState.choices),
    "kind": dict(ApprovalKind.choices),
}
BOOLEAN_FIELDS = {"confidentiality", "integrity", "availability"}


@register.filter
def lookup(mapping: dict[str, str], key: str) -> str:
    return mapping.get(key, key)


@register.simple_tag
def audit_value(field: str, value: str) -> str:
    if field in BOOLEAN_FIELDS:
        return {"True": "ja", "False": "nein"}.get(value, value)
    return VALUE_LABELS.get(field, {}).get(value, value)
