"""State machine of a risk (ESA 2 state diagram, decision 6): every pair of states is tested."""

from itertools import product

import pytest

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditEntry
from apps.risks.models import ApprovalKind, ApprovalRequest, Origin, Risk, RiskCategory, RiskStatus
from apps.risks.state_machine import (
    TRANSITIONS,
    GuardFailedError,
    TransitionError,
    TransitionForbiddenError,
    TransitionNotAllowedError,
    allowed_targets,
    transition,
)
from tests.conftest import MakeRisk

S = RiskStatus
pytestmark = [pytest.mark.req("SM"), pytest.mark.django_db]

# Copied from the specification on purpose — not imported — so a change to the code that is not
# also a change to the specification makes this test fail.
SPEC_ALLOWED = {
    (S.DRAFT, S.CATEGORIZED),
    (S.CATEGORIZED, S.SCORED),
    (S.SCORED, S.ESCALATED),
    (S.SCORED, S.VALIDATED),
    (S.ESCALATED, S.VALIDATED),
    (S.VALIDATED, S.CLOSED),
    (S.DRAFT, S.OBSOLETE),
    (S.CATEGORIZED, S.OBSOLETE),
    (S.SCORED, S.OBSOLETE),
    (S.VALIDATED, S.OBSOLETE),
    (S.CLOSED, S.OBSOLETE),
}
ALL_PAIRS = list(product(RiskStatus, RiskStatus))
FORBIDDEN_PAIRS = [pair for pair in ALL_PAIRS if pair not in SPEC_ALLOWED]


def test_sm_transition_table_matches_specification() -> None:
    assert set(TRANSITIONS) == SPEC_ALLOWED
    assert len(ALL_PAIRS) == 49
    assert len(FORBIDDEN_PAIRS) == 38


def _setup_for(
    pair: tuple[RiskStatus, RiskStatus], make_risk: MakeRisk, users: dict[str, User]
) -> tuple[Risk, User | None]:
    """A risk in the source state whose data satisfies the guard, plus a permitted actor."""
    source, _target = pair
    if pair == (S.CATEGORIZED, S.SCORED):
        risk = make_risk(source)
        risk.assessment.probability, risk.assessment.impact = 2, 3
        risk.assessment.save()
        return risk, users["rm"]
    if pair == (S.SCORED, S.ESCALATED):
        return make_risk(source, probability=4, impact=5), None
    if pair == (S.ESCALATED, S.VALIDATED):
        return make_risk(source, probability=4, impact=5, incident_response="Sperre"), users["ciso"]
    return make_risk(source), users["rm"]


@pytest.mark.parametrize(("source", "target"), sorted(SPEC_ALLOWED))
def test_sm_allowed_transition_succeeds(
    source: RiskStatus, target: RiskStatus, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk, actor = _setup_for((source, target), make_risk, users)

    transition(risk, target, actor)

    risk.refresh_from_db()
    assert risk.status == target


@pytest.mark.parametrize(("source", "target"), FORBIDDEN_PAIRS)
def test_sm_forbidden_transition_is_rejected_for_everyone(
    source: RiskStatus, target: RiskStatus, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(source, probability=4, impact=5, incident_response="dokumentiert")

    for actor in [*users.values(), None]:
        with pytest.raises(TransitionNotAllowedError):
            transition(risk, target, actor)

    risk.refresh_from_db()
    assert risk.status == source
    assert not AuditEntry.objects.filter(action=AuditAction.STATUS_CHANGED).exists()


def test_sm_escalated_cannot_become_obsolete(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.ESCALATED, probability=5, impact=5)
    with pytest.raises(TransitionNotAllowedError):
        transition(risk, S.OBSOLETE, users["rm"])


def test_sm_closed_cannot_return_to_draft(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.CLOSED)
    with pytest.raises(TransitionNotAllowedError):
        transition(risk, S.DRAFT, users["rm"])


def test_sm_allowed_targets() -> None:
    assert allowed_targets(S.ESCALATED) == {S.VALIDATED}
    assert allowed_targets(S.OBSOLETE) == set()
    assert allowed_targets(S.CLOSED) == {S.OBSOLETE}


# --- guards ---------------------------------------------------------------------------------


def test_sm_it_risk_never_escalates_even_at_25(make_risk: MakeRisk) -> None:
    risk = make_risk(S.SCORED, category=RiskCategory.IT_RISIKO, probability=5, impact=5)
    with pytest.raises(GuardFailedError):
        transition(risk, S.ESCALATED, None)


def test_sm_is_risk_below_20_does_not_escalate(make_risk: MakeRisk) -> None:
    risk = make_risk(S.SCORED, probability=4, impact=4)
    with pytest.raises(GuardFailedError):
        transition(risk, S.ESCALATED, None)


def test_sm_is_risk_at_20_cannot_skip_escalation(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.SCORED, probability=4, impact=5)
    with pytest.raises(GuardFailedError, match="muss eskaliert werden"):
        transition(risk, S.VALIDATED, users["rm"])


def test_sm_it_risk_at_25_is_validated_without_escalation(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.SCORED, category=RiskCategory.IT_RISIKO, probability=5, impact=5)
    transition(risk, S.VALIDATED, users["rm"])
    assert risk.status == S.VALIDATED


def test_sm_pending_approval_blocks_validation(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.SCORED)
    ApprovalRequest.objects.create(
        risk=risk,
        kind=ApprovalKind.CATEGORY_TO_IT,
        proposed_category=RiskCategory.IT_RISIKO,
        requested_by=users["nutzer"],
    )
    with pytest.raises(GuardFailedError, match="offene Freigabeanträge"):
        transition(risk, S.VALIDATED, users["rm"])


def test_sm_escalated_needs_documented_incident_response(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.ESCALATED, probability=5, impact=5, incident_response="   ")
    with pytest.raises(GuardFailedError, match="Incident Response"):
        transition(risk, S.VALIDATED, users["ciso"])


def test_sm_scoring_needs_probability_and_impact(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.CATEGORIZED)  # factory leaves P and I empty before SCORED
    with pytest.raises(GuardFailedError):
        transition(risk, S.SCORED, users["rm"])


def test_sm_categorizing_needs_origin(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.DRAFT)
    risk.assessment.origin = ""
    risk.assessment.save()
    with pytest.raises(
        GuardFailedError, match=r"^Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden$"
    ):
        transition(risk, S.CATEGORIZED, users["nutzer"])


def test_sm_categorizing_needs_a_protection_goal(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.DRAFT)
    cia = risk.assessment.cia
    cia.confidentiality = cia.integrity = cia.availability = False
    cia.save()
    with pytest.raises(GuardFailedError, match="Schutzziel"):
        transition(risk, S.CATEGORIZED, users["nutzer"])


def test_sm_is_risk_needs_assets(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.DRAFT)
    risk.assessment.assets.clear()
    with pytest.raises(GuardFailedError, match="Assets"):
        transition(risk, S.CATEGORIZED, users["nutzer"])


def test_sm_it_risk_needs_no_assets(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.DRAFT, category=RiskCategory.IT_RISIKO)
    risk.assessment.assets.clear()
    transition(risk, S.CATEGORIZED, users["nutzer"])
    assert risk.status == S.CATEGORIZED


# --- who may trigger what (M-05 at the level of the state machine) --------------------------


@pytest.mark.req("M-05")
def test_m_05_reporter_submits_own_draft_only(
    make_risk: MakeRisk, users: dict[str, User], make_user
) -> None:
    other = make_user(Role.NUTZER)
    own = make_risk(S.DRAFT, reporter=users["nutzer"])
    foreign = make_risk(S.DRAFT, reporter=other)

    transition(own, S.CATEGORIZED, users["nutzer"])
    with pytest.raises(TransitionForbiddenError):
        transition(foreign, S.CATEGORIZED, users["nutzer"])


@pytest.mark.req("M-05")
def test_m_05_reporter_cannot_score(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.CATEGORIZED, reporter=users["nutzer"])
    risk.assessment.probability, risk.assessment.impact = 2, 2
    risk.assessment.save()
    with pytest.raises(TransitionForbiddenError):
        transition(risk, S.SCORED, users["nutzer"])


@pytest.mark.req("M-05")
@pytest.mark.parametrize("role_key", ["nutzer", "rm", "rm2", "ciso", "admin"])
def test_m_05_escalation_is_triggered_by_the_system_only(
    role_key: str, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.SCORED, probability=5, impact=5)
    with pytest.raises(TransitionForbiddenError):
        transition(risk, S.ESCALATED, users[role_key])


@pytest.mark.req("M-05")
@pytest.mark.parametrize(("source", "target"), sorted(SPEC_ALLOWED - {(S.SCORED, S.ESCALATED)}))
def test_m_05_system_cannot_trigger_person_transitions(
    source: RiskStatus, target: RiskStatus, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk, _ = _setup_for((source, target), make_risk, users)
    with pytest.raises(TransitionForbiddenError):
        transition(risk, target, None)


@pytest.mark.req("M-05")
@pytest.mark.parametrize(("source", "target"), sorted(SPEC_ALLOWED - {(S.SCORED, S.ESCALATED)}))
def test_m_05_admin_has_no_say_in_the_risk_lifecycle(
    source: RiskStatus, target: RiskStatus, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk, _ = _setup_for((source, target), make_risk, users)
    with pytest.raises(TransitionForbiddenError):
        transition(risk, target, users["admin"])


@pytest.mark.req("M-05")
def test_m_05_inactive_user_is_rejected(make_risk: MakeRisk, users: dict[str, User]) -> None:
    users["rm"].is_active = False
    users["rm"].save()
    risk = make_risk(S.VALIDATED)
    with pytest.raises(TransitionForbiddenError):
        transition(risk, S.CLOSED, users["rm"])


# --- re-evaluation and audit ----------------------------------------------------------------


@pytest.mark.req("INV-03")
def test_sm_closed_to_obsolete_creates_successor_draft(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(S.CLOSED, probability=3, impact=3)

    successor = transition(risk, S.OBSOLETE, users["rm"])

    assert successor is not None
    risk.refresh_from_db()
    assert risk.status == S.OBSOLETE
    assert successor.status == S.DRAFT
    assert successor.predecessor_id == risk.pk
    assert successor.assessment.origin == Origin.DELIBERATE_ATTACK
    assert successor.assessment.cia.confidentiality is True
    assert list(successor.assessment.assets.all()) == list(risk.assessment.assets.all())
    # The new evaluation starts from scratch
    assert successor.assessment.score is None
    assert Risk.objects.count() == 2


def test_sm_validated_to_obsolete_successor_is_optional(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    without = make_risk(S.VALIDATED)
    with_successor = make_risk(S.VALIDATED)

    assert transition(without, S.OBSOLETE, users["rm"]) is None
    assert transition(with_successor, S.OBSOLETE, users["rm"], create_successor=True) is not None


def test_sm_successor_only_where_specified(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.SCORED)
    with pytest.raises(TransitionError):
        transition(risk, S.OBSOLETE, users["rm"], create_successor=True)
    risk.refresh_from_db()
    assert risk.status == S.SCORED


@pytest.mark.req("M-06")
def test_m_06_every_transition_is_audited(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(S.SCORED, probability=5, impact=4)

    transition(risk, S.ESCALATED, None)
    risk.incident_response = "Konten gesperrt"
    risk.save()
    transition(risk, S.VALIDATED, users["ciso"])

    entries = list(
        AuditEntry.objects.filter(risk=risk, action=AuditAction.STATUS_CHANGED).order_by(
            "created_at"
        )
    )
    assert [(e.actor, e.old_value, e.new_value) for e in entries] == [
        (None, S.SCORED, S.ESCALATED),
        (users["ciso"], S.ESCALATED, S.VALIDATED),
    ]
