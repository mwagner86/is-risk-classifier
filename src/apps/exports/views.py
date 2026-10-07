"""US-04a (CSV) and US-04b (PDF): two separate exports, both only for risk managers and only
filtered (M-07), both marked with exporter and time (M-08)."""

import re

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language, ngettext
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_safe

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.core.access import allow_roles
from apps.exports import pdf_client
from apps.exports.models import Export, ExportFormat
from apps.exports.rows import exporter_label, pdf_payload, risk_record, stamp, to_csv
from apps.risks.filters import RiskFilter
from apps.risks.levels import RiskLevel
from apps.risks.models import RiskCategory, RiskStatus
from apps.risks.services import visible_risks

FILTER_REQUIRED = _(
    "Bitte mindestens einen Filter setzen. Ein Export des gesamten Registers ist nicht vorgesehen."
)


def _user(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)  # noqa: S101 - DenyByDefaultMiddleware guarantees a login
    return user


@allow_roles(Role.RISK_MANAGER)
@require_safe
def export_page(request: HttpRequest) -> HttpResponse:
    user = _user(request)
    filters = RiskFilter.from_query(request.GET)
    count = None if filters.is_empty else filters.apply(visible_risks(user)).count()
    context = {
        "filters": filters,
        "count": count,
        "statuses": RiskStatus.choices,
        "categories": RiskCategory.choices,
        "levels": RiskLevel.choices,
        "recent": Export.objects.select_related("exported_by").order_by("-created_at")[:10],
    }
    return render(request, "exports/page.html", context)


def _export(request: HttpRequest, fmt: ExportFormat) -> HttpResponse:
    user = _user(request)
    filters = RiskFilter.from_query(request.GET)
    if filters.is_empty:
        messages.error(request, FILTER_REQUIRED)
        return redirect("export_page")
    risks = (
        filters.apply(visible_risks(user))
        .select_related("assessment", "assessment__cia", "reporter")
        .prefetch_related("assessment__assets")
        .order_by("created_at")
    )
    records = [risk_record(risk) for risk in risks]
    now = timezone.now()
    exporter, exported_at = exporter_label(user), stamp(now)

    if fmt == ExportFormat.CSV:
        content, content_type = to_csv(records, exporter, exported_at), "text/csv; charset=utf-8"
    else:
        payload = pdf_payload(records, exporter, exported_at, filters.describe(), get_language())
        try:
            content = pdf_client.render_pdf(payload)
        except pdf_client.PdfRenderError:
            messages.error(
                request, _("Das PDF konnte nicht erzeugt werden. Bitte später erneut versuchen.")
            )
            return redirect(f"{reverse('export_page')}?{filters.query_string()}")
        content_type = "application/pdf"

    with transaction.atomic():
        export = Export.objects.create(
            exported_by=user,
            format=fmt,
            filter_description=filters.describe(),
            query=filters.query_string(),
            row_count=len(records),
        )
        record(
            actor=user,
            action=AuditAction.EXPORTED,
            obj=export,
            field=fmt,
            new=f"{filters.describe()} · "
            + ngettext("%(count)d Risiko", "%(count)d Risiken", len(records))
            % {"count": len(records)},
        )

    safe_name = re.sub(r"[^A-Za-z0-9._-]", "_", user.username)
    filename = f"risiken_{timezone.localtime(now):%Y%m%d-%H%M}_{safe_name}.{fmt}"
    response = HttpResponse(content, content_type=content_type)
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"
    return response


@allow_roles(Role.RISK_MANAGER)
@require_safe
def export_csv(request: HttpRequest) -> HttpResponse:
    return _export(request, ExportFormat.CSV)


@allow_roles(Role.RISK_MANAGER)
@require_safe
def export_pdf(request: HttpRequest) -> HttpResponse:
    return _export(request, ExportFormat.PDF)
