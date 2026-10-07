"""Web layer for US-01 to US-03 and M-04. Views translate HTTP to service calls and back; the
services decide what is allowed."""

from uuid import UUID

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import Role, User
from apps.audit.views import FIELD_LABELS
from apps.core.access import allow_roles
from apps.core.forms import focus_first_error
from apps.notifications.services import resend_failed
from apps.risks import services
from apps.risks.dashboard import FLAG_ROLES, dashboard_data, only_failed, with_failure_flag
from apps.risks.filters import RiskFilter
from apps.risks.forms import ClassificationForm, IncidentResponseForm, RiskForm, ScoreForm
from apps.risks.levels import RiskLevel
from apps.risks.models import ApprovalState, Risk, RiskCategory, RiskStatus
from apps.risks.state_machine import (
    TRANSITIONS,
    TransitionError,
    TransitionForbiddenError,
    transition,
)

ALL_ROLES = tuple(Role)
CAPTURE_ROLES = (Role.NUTZER, Role.RISK_MANAGER)


def _user(request: HttpRequest) -> User:
    user = request.user
    assert isinstance(user, User)  # noqa: S101 - DenyByDefaultMiddleware guarantees a login
    return user


def _risk(request: HttpRequest, pk: UUID) -> Risk:
    risk: Risk = get_object_or_404(services.visible_risks(_user(request)), pk=pk)
    return risk


def _error_dict(exc: ValidationError) -> dict[str, list[str]]:
    return exc.message_dict if hasattr(exc, "error_dict") else {"__all__": exc.messages}


def _available_transitions(risk: Risk, user: User) -> list[RiskStatus]:
    """Targets the user may trigger by hand on this risk (guards are checked on submit)."""
    targets = []
    for (source, target), rule in TRANSITIONS.items():
        if source != risk.status or rule.system:
            continue
        # These have their own forms with the data they need
        if (source, target) in {
            (RiskStatus.DRAFT, RiskStatus.CATEGORIZED),
            (RiskStatus.CATEGORIZED, RiskStatus.SCORED),
            (RiskStatus.ESCALATED, RiskStatus.VALIDATED),
        }:
            continue
        own = risk.reporter_id == user.pk
        if user.role in rule.roles or (user.role in rule.owner_roles and own):
            targets.append(target)
    return targets


# --- list and detail ------------------------------------------------------------------------


@allow_roles(*ALL_ROLES)
def risk_list(request: HttpRequest) -> HttpResponse:
    risks = with_failure_flag(services.visible_risks(_user(request))).order_by("-created_at")
    filters = RiskFilter.from_query(request.GET)
    risks = filters.apply(risks)
    context = {
        "risks": risks,
        "filters": filters,
        "statuses": RiskStatus.choices,
        "categories": RiskCategory.choices,
        "levels": RiskLevel.choices,
        "show_failures": _user(request).role in FLAG_ROLES,
    }
    return render(request, "risks/list.html", context)


@allow_roles(*ALL_ROLES)
def dashboard(request: HttpRequest) -> HttpResponse:
    return render(request, "risks/dashboard.html", {"data": dashboard_data(_user(request))})


@allow_roles(*FLAG_ROLES)
def escalation_list(request: HttpRequest) -> HttpResponse:
    risks = with_failure_flag(services.visible_risks(_user(request)))
    context = {
        "failed_risks": only_failed(risks).order_by("-created_at"),
        "escalated_risks": risks.filter(status=RiskStatus.ESCALATED).order_by("-created_at"),
        "can_resend": _user(request).role == Role.ADMIN,
    }
    return render(request, "risks/escalations.html", context)


@allow_roles(Role.ADMIN)
@require_POST
def escalation_resend(request: HttpRequest, pk: UUID) -> HttpResponse:
    risk = _risk(request, pk)
    copies = resend_failed(risk, _user(request))
    if copies:
        messages.success(
            request, f"{len(copies)} Notifikation(en) erneut in die Warteschlange gestellt."
        )
    else:
        messages.info(
            request, "Keine fehlgeschlagene Notifikation offen oder bereits in der Warteschlange."
        )
    return redirect("escalation_list")


@allow_roles(*ALL_ROLES)
def risk_detail(request: HttpRequest, pk: UUID) -> HttpResponse:
    user = _user(request)
    risk = _risk(request, pk)
    context = {
        "risk": risk,
        "assessment": risk.assessment,
        "notifications": risk.notifications.order_by("created_at"),
        "approvals": risk.approval_requests.order_by("created_at"),
        "notification_failed": services.has_failed_notification(risk),
        "transitions": _available_transitions(risk, user),
        "can_edit_draft": risk.status == RiskStatus.DRAFT
        and (
            user.role == Role.RISK_MANAGER
            or (user.role == Role.NUTZER and risk.reporter_id == user.pk)
        ),
        "can_assess": user.role == Role.RISK_MANAGER and risk.status in services.EDITABLE,
        "can_document_ir": user.role in services.INCIDENT_ROLES
        and risk.status == RiskStatus.ESCALATED,
        "pending_approval": risk.approval_requests.filter(state=ApprovalState.PENDING).exists(),
        "history": risk.audit_entries.select_related("actor").order_by("-created_at")[:25]
        if user.role in FLAG_ROLES
        else None,
        "field_labels": FIELD_LABELS,
    }
    return render(request, "risks/detail.html", context)


# --- US-01: capture and draft ---------------------------------------------------------------


def _risk_form_response(
    request: HttpRequest, form: RiskForm, risk: Risk | None = None, status: int = 200
) -> HttpResponse:
    focus_first_error(form)
    return render(request, "risks/form.html", {"form": form, "risk": risk}, status=status)


def _save_risk_form(request: HttpRequest, form: RiskForm, risk: Risk | None) -> HttpResponse:
    user = _user(request)
    action = request.POST.get("action")
    if action not in {"submit", "draft"}:
        return HttpResponseBadRequest("Unbekannte Aktion.")
    data = {"title": form.cleaned_data["title"], "description": form.cleaned_data["description"]}
    data |= form.classification()
    try:
        if action == "draft":
            risk = services.save_draft(user, risk=risk, **data)
            messages.success(request, "Entwurf gespeichert.")
        elif risk is None:
            risk = services.capture(user, **data)
            messages.success(request, "Risiko gespeichert und kategorisiert.")
        else:
            services.save_draft(user, risk=risk, **data)
            services.submit(risk, user)
            messages.success(request, "Risiko gespeichert und kategorisiert.")
    except ValidationError as exc:
        form.add_service_errors(_error_dict(exc))
        return _risk_form_response(request, form, risk)
    return redirect("risk_detail", pk=risk.pk)


@allow_roles(*CAPTURE_ROLES)
def risk_create(request: HttpRequest) -> HttpResponse:
    form = RiskForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        return _save_risk_form(request, form, None)
    return _risk_form_response(request, form)


@allow_roles(*CAPTURE_ROLES)
def risk_edit(request: HttpRequest, pk: UUID) -> HttpResponse:
    risk = _risk(request, pk)
    if risk.status != RiskStatus.DRAFT:
        raise Http404
    assessment = risk.assessment
    initial = {
        "title": risk.title,
        "description": risk.description,
        "confidentiality": assessment.cia.confidentiality,
        "integrity": assessment.cia.integrity,
        "availability": assessment.cia.availability,
        "origin": assessment.origin,
        "assets": list(assessment.assets.all()),
    }
    form = RiskForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        return _save_risk_form(request, form, risk)
    return _risk_form_response(request, form, risk)


@allow_roles(*CAPTURE_ROLES)
@require_POST
def classification_preview(request: HttpRequest) -> HttpResponse:
    """HTMX: show the category the input yields and lock or unlock the assets field."""
    form = ClassificationForm(request.POST)
    return render(request, "risks/_classification.html", {"form": form})


@allow_roles(Role.RISK_MANAGER)
def risk_reclassify(request: HttpRequest, pk: UUID) -> HttpResponse:
    risk = _risk(request, pk)
    if risk.status not in services.EDITABLE:
        raise Http404
    assessment = risk.assessment
    initial = {
        "confidentiality": assessment.cia.confidentiality,
        "integrity": assessment.cia.integrity,
        "availability": assessment.cia.availability,
        "origin": assessment.origin,
        "assets": list(assessment.assets.all()),
    }
    form = ClassificationForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            services.reclassify(risk, _user(request), **form.classification())
        except ValidationError as exc:
            form.add_service_errors(_error_dict(exc))
        else:
            messages.success(request, "Klassifizierung gespeichert.")
            return redirect("risk_detail", pk=risk.pk)
    focus_first_error(form)
    return render(request, "risks/reclassify.html", {"form": form, "risk": risk})


# --- US-02: score ---------------------------------------------------------------------------


@allow_roles(Role.RISK_MANAGER)
def risk_score(request: HttpRequest, pk: UUID) -> HttpResponse:
    risk = _risk(request, pk)
    if risk.status not in services.EDITABLE:
        raise Http404
    assessment = risk.assessment
    form = ScoreForm(
        request.POST or None,
        initial={"probability": assessment.probability, "impact": assessment.impact},
    )
    if request.method == "POST" and form.is_valid():
        try:
            pending = services.score(
                risk,
                _user(request),
                probability=form.cleaned_data["probability"],
                impact=form.cleaned_data["impact"],
            )
        except ValidationError as exc:
            for field, errors in _error_dict(exc).items():
                for error in errors:
                    form.add_error(field if field in form.fields else None, error)
        else:
            if pending:
                messages.warning(
                    request,
                    "Herabstufung unter 20 beantragt. Sie wird wirksam, sobald ein anderer "
                    "Risk Manager sie freigibt.",
                )
            else:
                messages.success(request, "Bewertung gespeichert.")
            return redirect("risk_detail", pk=risk.pk)
    focus_first_error(form)
    preview = form.preview() if form.is_bound else assessment.score
    return render(request, "risks/score.html", {"form": form, "risk": risk, "preview": preview})


@allow_roles(Role.RISK_MANAGER)
@require_POST
def score_preview(request: HttpRequest) -> HttpResponse:
    """HTMX: live R = P x I, or "Nicht berechenbar" (AK-02.3)."""
    return render(
        request, "risks/_score_preview.html", {"preview": ScoreForm(request.POST).preview()}
    )


# --- status changes -------------------------------------------------------------------------


@allow_roles(Role.NUTZER, Role.RISK_MANAGER, Role.CISO)
@require_POST
def risk_change_status(request: HttpRequest, pk: UUID) -> HttpResponse:
    risk = _risk(request, pk)
    try:
        target = RiskStatus(request.POST.get("target", ""))
    except ValueError:
        return HttpResponseBadRequest("Unbekannter Zielstatus.")
    try:
        successor = transition(
            risk, target, _user(request), create_successor=request.POST.get("successor") == "on"
        )
    except TransitionForbiddenError as exc:
        raise PermissionDenied(str(exc)) from exc
    except TransitionError as exc:
        messages.error(request, str(exc))
        return redirect("risk_detail", pk=risk.pk)
    if successor is not None:
        messages.success(
            request, "Risiko ist obsolet. Ein neuer Entwurf zur Neubewertung liegt an."
        )
        return redirect("risk_detail", pk=successor.pk)
    messages.success(request, f"Status: {target.label}.")
    return redirect("risk_detail", pk=risk.pk)


@allow_roles(Role.RISK_MANAGER, Role.CISO)
def risk_incident_response(request: HttpRequest, pk: UUID) -> HttpResponse:
    risk = _risk(request, pk)
    if risk.status != RiskStatus.ESCALATED:
        raise Http404
    form = IncidentResponseForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        try:
            services.document_incident_response(
                risk, _user(request), form.cleaned_data["incident_response"]
            )
        except ValidationError as exc:
            for field, errors in _error_dict(exc).items():
                for error in errors:
                    form.add_error(field if field in form.fields else None, error)
        else:
            messages.success(request, "Incident Response dokumentiert, Risiko validiert.")
            return redirect("risk_detail", pk=risk.pk)
    focus_first_error(form)
    return render(request, "risks/incident_response.html", {"form": form, "risk": risk})


# --- M-04: approvals ------------------------------------------------------------------------


@allow_roles(Role.RISK_MANAGER)
def approval_list(request: HttpRequest) -> HttpResponse:
    approvals = services.pending_approvals_for(_user(request)).order_by("created_at")
    return render(request, "risks/approvals.html", {"approvals": approvals})


@allow_roles(Role.RISK_MANAGER)
@require_POST
def approval_decide(request: HttpRequest, pk: UUID) -> HttpResponse:
    approval = get_object_or_404(services.pending_approvals_for(_user(request)), pk=pk)
    decision = request.POST.get("decision")
    if decision not in {"approve", "reject"}:
        return HttpResponseBadRequest("Unbekannte Entscheidung.")
    try:
        services.decide(approval, _user(request), approve=decision == "approve")
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Freigegeben." if decision == "approve" else "Abgelehnt.")
    return redirect("approval_list")
