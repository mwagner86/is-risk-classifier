"""Use cases of the risk register: capture (US-01), scoring (US-02), escalation (US-03) and the
approval of relaxations (M-04).

Views call only these functions. Each one checks the actor's role itself (M-05), validates on the
server whatever the browser already checked, and writes every change of protection goals, origin,
P and I to the audit log (M-06).
"""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.cmdb.models import Asset
from apps.core.models import BaseModel
from apps.notifications.models import NotificationStatus
from apps.notifications.services import enqueue_escalation, enqueue_it_handover
from apps.risks.classification import categorize
from apps.risks.models import (
    ESCALATION_THRESHOLD,
    SCALE_MAX,
    SCALE_MIN,
    ApprovalKind,
    ApprovalRequest,
    ApprovalState,
    CIATriad,
    Origin,
    Risk,
    RiskAssessment,
    RiskCategory,
    RiskStatus,
)
from apps.risks.state_machine import requires_escalation, transition

ORIGIN_MISSING = "Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden"
ORIGIN_UNKNOWN = "Unbekannter Ursprung."
GOAL_MISSING = "Mindestens ein Schutzziel muss ausgewählt werden."
ASSETS_MISSING = "Für ein IS-Risiko müssen die betroffenen Assets angegeben werden."
TITLE_MISSING = "Bitte einen Titel angeben."
DESCRIPTION_MISSING = "Bitte eine Beschreibung angeben."
RANGE_MESSAGES = {
    "probability": "Zulässiger Wertebereich für die Eintrittswahrscheinlichkeit ist 1 bis 5",
    "impact": "Zulässiger Wertebereich für das Schadensausmaß ist 1 bis 5",
}
NOT_EDITABLE = "In diesem Status kann die Bewertung nicht mehr geändert werden."

CAPTURE_ROLES = frozenset({Role.NUTZER, Role.RISK_MANAGER})
RM = frozenset({Role.RISK_MANAGER})
INCIDENT_ROLES = frozenset({Role.RISK_MANAGER, Role.CISO})
# Statuses in which classification and score may still change (decision 6)
EDITABLE = frozenset({RiskStatus.CATEGORIZED, RiskStatus.SCORED, RiskStatus.ESCALATED})


@dataclass(frozen=True)
class Classification:
    confidentiality: bool
    integrity: bool
    availability: bool
    origin: str
    assets: tuple[Asset, ...]

    @property
    def category(self) -> RiskCategory | None:
        return categorize(self.confidentiality, self.integrity, self.availability, self.origin)

    def errors(self) -> dict[str, list[str]]:
        errors: dict[str, list[str]] = {}
        if not (self.confidentiality or self.integrity or self.availability):
            errors["cia"] = [GOAL_MISSING]
        if not self.origin:
            errors["origin"] = [ORIGIN_MISSING]
        elif self.origin not in Origin.values:
            errors["origin"] = [ORIGIN_UNKNOWN]
        if self.category == RiskCategory.IS_RISIKO and not self.assets:
            errors["assets"] = [ASSETS_MISSING]
        return errors


def _classification(
    confidentiality: bool, integrity: bool, availability: bool, origin: str, assets: Iterable[Asset]
) -> Classification:
    return Classification(
        bool(confidentiality), bool(integrity), bool(availability), origin or "", tuple(assets)
    )


def _require_role(actor: User, roles: frozenset[Role]) -> None:
    if not actor.is_active or actor.role not in roles:
        raise PermissionDenied("Keine Berechtigung für diese Aktion.")


def _text_errors(title: str, description: str) -> dict[str, list[str]]:
    errors: dict[str, list[str]] = {}
    if not title.strip():
        errors["title"] = [TITLE_MISSING]
    if not description.strip():
        errors["description"] = [DESCRIPTION_MISSING]
    return errors


def _apply(actor: User | None, risk: Risk, obj: BaseModel, values: dict[str, Any]) -> bool:
    """Set ``values`` on ``obj`` and audit every field that actually changes (M-06)."""
    changed = []
    for field, new in values.items():
        old = getattr(obj, field)
        if old != new:
            setattr(obj, field, new)
            record(
                actor=actor,
                action=AuditAction.FIELD_CHANGED,
                obj=obj,
                risk=risk,
                field=field,
                old=old,
                new=new,
            )
            changed.append(field)
    if changed:
        obj.save()
    return bool(changed)


def _set_assets(
    actor: User, risk: Risk, assessment: RiskAssessment, assets: Iterable[Asset]
) -> None:
    old = sorted(a.cmdb_key for a in assessment.assets.all())
    new_assets = list(assets)
    new = sorted(a.cmdb_key for a in new_assets)
    if old != new:
        assessment.assets.set(new_assets)
        record(
            actor=actor,
            action=AuditAction.FIELD_CHANGED,
            obj=assessment,
            risk=risk,
            field="assets",
            old=", ".join(old),
            new=", ".join(new),
        )


def _lock(risk: Risk) -> Risk:
    # Lock the risk row only; the joined assessment sits on the nullable side of an outer join
    locked: Risk = (
        Risk.objects.select_for_update(of=("self",))
        .select_related("assessment", "assessment__cia")
        .get(pk=risk.pk)
    )
    return locked


def _request(risk: Risk, actor: User, kind: ApprovalKind, **proposal: Any) -> ApprovalRequest:
    request = ApprovalRequest.objects.create(risk=risk, kind=kind, requested_by=actor, **proposal)
    record(
        actor=actor,
        action=AuditAction.APPROVAL_REQUESTED,
        obj=request,
        risk=risk,
        field="kind",
        new=kind,
    )
    return request


def _withdraw(risk: Risk, kind: ApprovalKind) -> None:
    for request in risk.approval_requests.filter(kind=kind, state=ApprovalState.PENDING):
        request.state = ApprovalState.WITHDRAWN
        request.decided_at = timezone.now()
        request.save(update_fields=["state", "decided_at"])
        record(
            actor=None,
            action=AuditAction.APPROVAL_DECIDED,
            obj=request,
            risk=risk,
            field="state",
            old=ApprovalState.PENDING,
            new=ApprovalState.WITHDRAWN,
        )


def _apply_category(
    actor: User, risk: Risk, assessment: RiskAssessment, computed: RiskCategory
) -> None:
    """IS takes effect at once; IT only after approval (M-04), until then IS applies."""
    if computed == RiskCategory.IS_RISIKO:
        _apply(actor, risk, assessment, {"category": RiskCategory.IS_RISIKO})
        _withdraw(risk, ApprovalKind.CATEGORY_TO_IT)
        return
    if assessment.category == RiskCategory.IT_RISIKO:
        return
    _apply(actor, risk, assessment, {"category": RiskCategory.IS_RISIKO})
    pending = risk.approval_requests.filter(
        kind=ApprovalKind.CATEGORY_TO_IT, state=ApprovalState.PENDING
    )
    if not pending.exists():
        _request(risk, actor, ApprovalKind.CATEGORY_TO_IT, proposed_category=RiskCategory.IT_RISIKO)


def _escalate_if_required(risk: Risk) -> None:
    risk.refresh_from_db(fields=["status"])
    if risk.status == RiskStatus.SCORED and requires_escalation(risk):
        transition(risk, RiskStatus.ESCALATED, None)
        enqueue_escalation(risk)


# --- queries --------------------------------------------------------------------------------


def visible_risks(user: User) -> QuerySet[Risk]:
    """Reporters see their own risks only; the other roles see the register."""
    risks = Risk.objects.select_related("assessment", "reporter")
    if user.role == Role.NUTZER:
        return risks.filter(reporter=user)
    return risks


def pending_approvals_for(user: User) -> QuerySet[ApprovalRequest]:
    """Requests this risk manager may decide: pending and not their own (M-04)."""
    if user.role != Role.RISK_MANAGER:
        return ApprovalRequest.objects.none()
    return (
        ApprovalRequest.objects.select_related("risk", "requested_by")
        .filter(state=ApprovalState.PENDING)
        .exclude(requested_by=user)
    )


def has_failed_notification(risk: Risk) -> bool:
    """AK-03.3: a failed delivery keeps the risk flagged."""
    return risk.notifications.filter(status=NotificationStatus.FAILED).exists()


# --- US-01: capture -------------------------------------------------------------------------


def _create_draft(reporter: User, title: str, description: str, c: Classification) -> Risk:
    risk = Risk.objects.create(title=title, description=description, reporter=reporter)
    assessment = RiskAssessment.objects.create(risk=risk, origin=c.origin)
    CIATriad.objects.create(
        assessment=assessment,
        confidentiality=c.confidentiality,
        integrity=c.integrity,
        availability=c.availability,
    )
    assessment.assets.set(c.assets)
    record(actor=reporter, action=AuditAction.CREATED, obj=risk, risk=risk)
    return risk


@transaction.atomic
def save_draft(
    actor: User,
    *,
    title: str,
    description: str = "",
    confidentiality: bool = False,
    integrity: bool = False,
    availability: bool = False,
    origin: str = "",
    assets: Iterable[Asset] = (),
    risk: Risk | None = None,
) -> Risk:
    """Store a DRAFT without the US-01 checks; only a title is needed."""
    _require_role(actor, CAPTURE_ROLES)
    if not title.strip():
        raise ValidationError({"title": [TITLE_MISSING]})
    c = _classification(confidentiality, integrity, availability, origin, assets)
    if c.origin and c.origin not in Origin.values:
        raise ValidationError({"origin": [ORIGIN_UNKNOWN]})
    if risk is None:
        return _create_draft(actor, title, description, c)
    risk = _check_draft_access(risk, actor)
    _apply(actor, risk, risk, {"title": title, "description": description})
    assessment = risk.assessment
    _apply(
        actor,
        risk,
        assessment.cia,
        {
            "confidentiality": c.confidentiality,
            "integrity": c.integrity,
            "availability": c.availability,
        },
    )
    _apply(actor, risk, assessment, {"origin": c.origin})
    _set_assets(actor, risk, assessment, c.assets)
    return risk


def _check_draft_access(risk: Risk, actor: User) -> Risk:
    locked = _lock(risk)
    if locked.status != RiskStatus.DRAFT:
        raise ValidationError("Nur Entwürfe können bearbeitet werden.")
    if actor.role == Role.NUTZER and locked.reporter_id != actor.pk:
        raise PermissionDenied("Keine Berechtigung für diese Aktion.")
    return locked


@transaction.atomic
def submit(risk: Risk, actor: User) -> Risk:
    """DRAFT -> CATEGORIZED: check US-01, set the category and request approval for IT."""
    _require_role(actor, CAPTURE_ROLES)
    risk = _check_draft_access(risk, actor)
    assessment = risk.assessment
    cia = assessment.cia
    c = _classification(
        cia.confidentiality,
        cia.integrity,
        cia.availability,
        assessment.origin,
        assessment.assets.all(),
    )
    errors = _text_errors(risk.title, risk.description) | c.errors()
    if errors:
        raise ValidationError(errors)
    assert c.category is not None  # noqa: S101 - guaranteed by c.errors()
    _apply_category(actor, risk, assessment, c.category)
    transition(risk, RiskStatus.CATEGORIZED, actor)
    return risk


@transaction.atomic
def capture(
    reporter: User,
    *,
    title: str,
    description: str,
    confidentiality: bool,
    integrity: bool,
    availability: bool,
    origin: str,
    assets: Iterable[Asset],
) -> Risk:
    """Capture and submit in one step. Nothing is stored if a check fails (AK-01.3)."""
    _require_role(reporter, CAPTURE_ROLES)
    c = _classification(confidentiality, integrity, availability, origin, assets)
    errors = _text_errors(title, description) | c.errors()
    if errors:
        raise ValidationError(errors)
    risk = _create_draft(reporter, title, description, c)
    return submit(risk, reporter)


@transaction.atomic
def reclassify(
    risk: Risk,
    actor: User,
    *,
    confidentiality: bool,
    integrity: bool,
    availability: bool,
    origin: str,
    assets: Iterable[Asset],
) -> None:
    """Change protection goals, origin and assets of a submitted risk (risk manager only)."""
    _require_role(actor, RM)
    risk = _lock(risk)
    if risk.status not in EDITABLE:
        raise ValidationError(NOT_EDITABLE)
    c = _classification(confidentiality, integrity, availability, origin, assets)
    if errors := c.errors():
        raise ValidationError(errors)
    assert c.category is not None  # noqa: S101 - guaranteed by c.errors()
    assessment = risk.assessment
    _apply(
        actor,
        risk,
        assessment.cia,
        {
            "confidentiality": c.confidentiality,
            "integrity": c.integrity,
            "availability": c.availability,
        },
    )
    _apply(actor, risk, assessment, {"origin": c.origin})
    _set_assets(actor, risk, assessment, c.assets)
    _apply_category(actor, risk, assessment, c.category)
    _escalate_if_required(risk)


# --- US-02: score ---------------------------------------------------------------------------


def _scale_value(field: str, value: object) -> int | None:
    """Server-side check of P and I: an int from 1 to 5, nothing else (AK-02.2, AK-02.3)."""
    if type(value) is not int or not SCALE_MIN <= value <= SCALE_MAX:
        return None
    return value


@transaction.atomic
def score(
    risk: Risk, actor: User, *, probability: object, impact: object
) -> ApprovalRequest | None:
    """Set P and I. A downgrade of an IS risk below 20 is only requested (M-04).

    Returns the approval request if one was created instead of applying the values.
    """
    _require_role(actor, RM)
    values = {
        "probability": _scale_value("probability", probability),
        "impact": _scale_value("impact", impact),
    }
    errors = {field: [RANGE_MESSAGES[field]] for field, value in values.items() if value is None}
    if errors:
        raise ValidationError(errors)
    p, i = values["probability"], values["impact"]
    assert p is not None and i is not None  # noqa: S101 - checked above
    risk = _lock(risk)
    if risk.status not in EDITABLE:
        raise ValidationError(NOT_EDITABLE)
    assessment = risk.assessment

    is_downgrade = (
        assessment.category == RiskCategory.IS_RISIKO
        and assessment.score is not None
        and assessment.score >= ESCALATION_THRESHOLD
        and p * i < ESCALATION_THRESHOLD
    )
    if is_downgrade:
        _withdraw(risk, ApprovalKind.SCORE_DOWNGRADE)
        return _request(
            risk,
            actor,
            ApprovalKind.SCORE_DOWNGRADE,
            proposed_probability=p,
            proposed_impact=i,
        )

    _apply(actor, risk, assessment, {"probability": p, "impact": i})
    if risk.status == RiskStatus.CATEGORIZED:
        transition(risk, RiskStatus.SCORED, actor)
    _escalate_if_required(risk)
    return None


# --- M-04: decide on a request --------------------------------------------------------------


@transaction.atomic
def decide(request: ApprovalRequest, actor: User, *, approve: bool) -> None:
    _require_role(actor, RM)
    request = ApprovalRequest.objects.select_for_update().get(pk=request.pk)
    if request.state != ApprovalState.PENDING:
        raise ValidationError("Über diesen Antrag wurde bereits entschieden.")
    if request.requested_by_id == actor.pk:
        raise PermissionDenied("Eigene Anträge gibt ein anderer Risk Manager frei.")
    risk = _lock(request.risk)
    if approve and risk.status not in EDITABLE:
        raise ValidationError(NOT_EDITABLE)

    request.state = ApprovalState.APPROVED if approve else ApprovalState.REJECTED
    request.decided_by = actor
    request.decided_at = timezone.now()
    request.save(update_fields=["state", "decided_by", "decided_at"])
    record(
        actor=actor,
        action=AuditAction.APPROVAL_DECIDED,
        obj=request,
        risk=risk,
        field="state",
        old=ApprovalState.PENDING,
        new=request.state,
    )
    if not approve:
        return

    assessment = risk.assessment
    # The requester is the author of the new value; the approver is in the decision entry above
    author = request.requested_by
    if request.kind == ApprovalKind.CATEGORY_TO_IT:
        _apply(author, risk, assessment, {"category": RiskCategory.IT_RISIKO})
        enqueue_it_handover(risk)
    else:
        _apply(
            author,
            risk,
            assessment,
            {"probability": request.proposed_probability, "impact": request.proposed_impact},
        )


# --- US-03: close an escalation -------------------------------------------------------------


@transaction.atomic
def document_incident_response(risk: Risk, actor: User, text: str) -> None:
    """ESCALATED -> VALIDATED, only with documented incident response."""
    _require_role(actor, INCIDENT_ROLES)
    if not text.strip():
        raise ValidationError({"incident_response": ["Bitte die Incident Response dokumentieren."]})
    risk = _lock(risk)
    if risk.status != RiskStatus.ESCALATED:
        raise ValidationError("Nur eskalierte Risiken erhalten eine Incident Response.")
    _apply(actor, risk, risk, {"incident_response": text.strip()})
    transition(risk, RiskStatus.VALIDATED, actor)
