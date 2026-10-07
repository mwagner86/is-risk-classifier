"""The one place where a risk changes its status (state diagram of ESA 2, decision 6).

Every transition is listed in ``TRANSITIONS`` with the roles that may trigger it and a guard.
Anything not listed is rejected — including ESCALATED -> OBSOLETE and CLOSED -> DRAFT.
"""

from collections.abc import Callable
from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.risks.classification import categorize
from apps.risks.models import (
    ESCALATION_THRESHOLD,
    ApprovalState,
    CIATriad,
    Risk,
    RiskAssessment,
    RiskCategory,
    RiskStatus,
)

S = RiskStatus

# A guard returns None when the transition may happen, otherwise the reason (German, for the UI).
Guard = Callable[[Risk], str | None]


class TransitionError(Exception):
    pass


class TransitionNotAllowedError(TransitionError):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(
            gettext("Übergang von %(source)s nach %(target)s ist nicht zulässig.")
            % {"source": RiskStatus(source).label, "target": RiskStatus(target).label}
        )


class TransitionForbiddenError(TransitionError):
    def __init__(self, source: str, target: str) -> None:
        super().__init__(
            gettext("Keine Berechtigung für den Übergang von %(source)s nach %(target)s.")
            % {"source": RiskStatus(source).label, "target": RiskStatus(target).label}
        )


class GuardFailedError(TransitionError):
    pass


@dataclass(frozen=True)
class Transition:
    source: RiskStatus
    target: RiskStatus
    # Roles that may trigger the transition on any risk
    roles: frozenset[Role] = frozenset()
    # Roles that may trigger it only on risks they reported themselves
    owner_roles: frozenset[Role] = frozenset()
    # Triggered by the system itself (actor None), never by a person
    system: bool = False
    guard: Guard | None = None


def _assessment(risk: Risk) -> RiskAssessment | None:
    try:
        return risk.assessment
    except RiskAssessment.DoesNotExist:
        return None


def _cia(assessment: RiskAssessment) -> CIATriad | None:
    try:
        return assessment.cia
    except CIATriad.DoesNotExist:
        return None


def is_categorized(risk: Risk) -> str | None:
    assessment = _assessment(risk)
    if assessment is None:
        return gettext("Es fehlt die Bewertung.")
    cia = _cia(assessment)
    if cia is None or not cia.any_affected:
        return gettext("Mindestens ein Schutzziel muss ausgewählt sein.")
    if not assessment.origin:
        return gettext("Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden")
    if assessment.category is None:
        return gettext("Die Kategorie ist noch nicht bestimmt.")
    # Assets follow the rule's result: a requested IT categorisation needs none, even though
    # the risk counts as IS until the request is approved (M-04)
    computed = categorize(cia.confidentiality, cia.integrity, cia.availability, assessment.origin)
    if computed == RiskCategory.IS_RISIKO and not assessment.assets.exists():
        return gettext("Für ein IS-Risiko müssen die betroffenen Assets angegeben werden.")
    return None


def is_scored(risk: Risk) -> str | None:
    assessment = _assessment(risk)
    if assessment is None or assessment.score is None:
        return gettext("Eintrittswahrscheinlichkeit und Schadensausmaß müssen gesetzt sein.")
    return None


def requires_escalation(risk: Risk) -> bool:
    assessment = _assessment(risk)
    return (
        assessment is not None
        and assessment.category == RiskCategory.IS_RISIKO
        and assessment.score is not None
        and assessment.score >= ESCALATION_THRESHOLD
    )


def must_escalate(risk: Risk) -> str | None:
    if not requires_escalation(risk):
        return gettext("Eskaliert werden nur IS-Risiken mit einem Risikowert ab 20.")
    return None


def may_validate_without_escalation(risk: Risk) -> str | None:
    if requires_escalation(risk):
        return gettext("Ein IS-Risiko mit einem Risikowert ab 20 muss eskaliert werden.")
    if risk.approval_requests.filter(state=ApprovalState.PENDING).exists():
        return gettext("Es gibt offene Freigabeanträge.")
    return None


def incident_response_documented(risk: Risk) -> str | None:
    if not risk.incident_response.strip():
        return gettext("Die Incident Response muss dokumentiert sein.")
    return None


RM = frozenset({Role.RISK_MANAGER})

TRANSITIONS: dict[tuple[RiskStatus, RiskStatus], Transition] = {
    (t.source, t.target): t
    for t in (
        Transition(S.DRAFT, S.CATEGORIZED, RM, frozenset({Role.NUTZER}), guard=is_categorized),
        Transition(S.CATEGORIZED, S.SCORED, RM, guard=is_scored),
        Transition(S.SCORED, S.ESCALATED, system=True, guard=must_escalate),
        Transition(S.SCORED, S.VALIDATED, RM, guard=may_validate_without_escalation),
        Transition(
            S.ESCALATED,
            S.VALIDATED,
            frozenset({Role.RISK_MANAGER, Role.CISO}),
            guard=incident_response_documented,
        ),
        Transition(S.VALIDATED, S.CLOSED, RM),
        Transition(S.DRAFT, S.OBSOLETE, RM, frozenset({Role.NUTZER})),
        Transition(S.CATEGORIZED, S.OBSOLETE, RM),
        Transition(S.SCORED, S.OBSOLETE, RM),
        Transition(S.VALIDATED, S.OBSOLETE, RM),
        Transition(S.CLOSED, S.OBSOLETE, RM),
    )
}

# Re-evaluation: these transitions supersede the risk with a new DRAFT (always for CLOSED,
# optionally for VALIDATED — extension agreed in decision 6).
SUCCESSOR_ALWAYS = {(S.CLOSED, S.OBSOLETE)}
SUCCESSOR_OPTIONAL = {(S.VALIDATED, S.OBSOLETE)}


def allowed_targets(status: RiskStatus) -> frozenset[RiskStatus]:
    return frozenset(target for source, target in TRANSITIONS if source == status)


def _check_actor(transition: Transition, risk: Risk, actor: User | None) -> None:
    if actor is None:
        if not transition.system:
            raise TransitionForbiddenError(transition.source, transition.target)
        return
    if transition.system or not actor.is_active:
        raise TransitionForbiddenError(transition.source, transition.target)
    if actor.role in transition.roles:
        return
    if actor.role in transition.owner_roles and risk.reporter_id == actor.pk:
        return
    raise TransitionForbiddenError(transition.source, transition.target)


def _create_successor(risk: Risk, actor: User) -> Risk:
    successor = Risk.objects.create(
        title=risk.title,
        description=risk.description,
        reporter=actor,
        predecessor=risk,
    )
    old = _assessment(risk)
    new = RiskAssessment.objects.create(risk=successor, origin=old.origin if old else "")
    old_cia = _cia(old) if old else None
    CIATriad.objects.create(
        assessment=new,
        confidentiality=old_cia.confidentiality if old_cia else False,
        integrity=old_cia.integrity if old_cia else False,
        availability=old_cia.availability if old_cia else False,
    )
    if old:
        new.assets.set(old.assets.all())
    record(actor=actor, action=AuditAction.CREATED, obj=successor, risk=successor, old=risk.pk)
    return successor


def transition(
    risk: Risk,
    target: RiskStatus,
    actor: User | None,
    *,
    create_successor: bool = False,
) -> Risk | None:
    """Move ``risk`` to ``target``. Returns the new DRAFT if a successor was created."""
    with transaction.atomic():
        # Lock the row so two concurrent requests cannot both pass the guard
        locked = Risk.objects.select_for_update().get(pk=risk.pk)
        source = RiskStatus(locked.status)
        rule = TRANSITIONS.get((source, target))
        if rule is None:
            raise TransitionNotAllowedError(source, target)
        _check_actor(rule, locked, actor)
        if rule.guard is not None and (reason := rule.guard(locked)) is not None:
            raise GuardFailedError(reason)
        if create_successor and (source, target) not in SUCCESSOR_OPTIONAL:
            raise TransitionError(gettext("Für diesen Übergang ist kein Nachfolger vorgesehen."))

        locked.status = target
        locked.save(update_fields=["status"])
        record(
            actor=actor,
            action=AuditAction.STATUS_CHANGED,
            obj=locked,
            risk=locked,
            field="status",
            old=source,
            new=target,
        )
        risk.status = target

        if (source, target) in SUCCESSOR_ALWAYS or create_successor:
            assert actor is not None  # noqa: S101 - only person-triggered transitions get here
            return _create_successor(locked, actor)
    return None
