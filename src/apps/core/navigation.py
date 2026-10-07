"""Sidebar entries per role. Visibility here is convenience only; every view checks its roles
itself (M-05)."""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.http import HttpRequest
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import Role

if TYPE_CHECKING:
    from django_stubs_ext import StrOrPromise
else:
    StrOrPromise = str

ALL = frozenset(Role)


@dataclass(frozen=True)
class NavItem:
    label: StrOrPromise
    url_name: str
    icon: str
    roles: frozenset[Role]
    # Further URL names that count as "inside" this entry
    section: tuple[str, ...] = ()


NAVIGATION = (
    NavItem(_("Dashboard"), "dashboard", "grid", ALL),
    NavItem(
        _("Risiken"),
        "risk_list",
        "list",
        ALL,
        (
            "risk_create",
            "risk_detail",
            "risk_edit",
            "risk_score",
            "risk_reclassify",
            "risk_incident_response",
        ),
    ),
    NavItem(_("Assets"), "asset_list", "server", ALL),
    NavItem(
        _("Eskalationen"),
        "escalation_list",
        "alert",
        frozenset({Role.RISK_MANAGER, Role.CISO, Role.ADMIN}),
    ),
    NavItem(_("Freigaben"), "approval_list", "check", frozenset({Role.RISK_MANAGER})),
    NavItem(
        _("Audit-Log"),
        "audit_log",
        "history",
        frozenset({Role.RISK_MANAGER, Role.CISO, Role.ADMIN}),
    ),
    NavItem(_("Export"), "export_page", "download", frozenset({Role.RISK_MANAGER})),
)


def navigation(request: HttpRequest) -> dict[str, Any]:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    current = request.resolver_match.url_name if request.resolver_match else None
    items = [
        {
            "label": item.label,
            "url": reverse(item.url_name),
            "icon": item.icon,
            "active": current == item.url_name or current in item.section,
        }
        for item in NAVIGATION
        if user.role in item.roles
    ]
    return {"nav_items": items}
