"""M-04: IT categorisation and a downgrade below 20 take effect only after a second risk manager
approved them; until then the stricter classification applies."""

from typing import Any

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.risks.models import ApprovalKind, ApprovalState, Origin, RiskCategory, RiskStatus
from apps.risks.services import decide, reclassify, score
from tests.conftest import MakeRisk

pytestmark = [pytest.mark.req("M-04"), pytest.mark.django_db]

IT_CLASSIFICATION: dict[str, Any] = {
    "confidentiality": False,
    "integrity": False,
    "availability": True,
    "origin": Origin.TECHNICAL_FAILURE,
    "assets": [],
}


def test_m_04_pending_it_categorisation_still_escalates(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    reclassify(risk, users["rm"], **IT_CLASSIFICATION)

    score(risk, users["rm2"], probability=4, impact=5)

    risk.refresh_from_db()
    assert risk.assessment.category == RiskCategory.IS_RISIKO
    assert risk.status == RiskStatus.ESCALATED


def test_m_04_requester_cannot_approve_own_request(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.SCORED)
    reclassify(risk, users["rm"], **IT_CLASSIFICATION)
    request = risk.approval_requests.get()

    with pytest.raises(PermissionDenied):
        decide(request, users["rm"], approve=True)

    decide(request, users["rm2"], approve=True)
    risk.assessment.refresh_from_db()
    assert risk.assessment.category == RiskCategory.IT_RISIKO


@pytest.mark.parametrize("role_key", ["nutzer", "ciso", "admin"])
def test_m_04_only_risk_managers_decide(
    role_key: str, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.SCORED)
    reclassify(risk, users["rm"], **IT_CLASSIFICATION)
    with pytest.raises(PermissionDenied):
        decide(risk.approval_requests.get(), users[role_key], approve=True)


def test_m_04_rejected_request_keeps_is_risk(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(RiskStatus.SCORED)
    reclassify(risk, users["rm"], **IT_CLASSIFICATION)
    request = risk.approval_requests.get()

    decide(request, users["rm2"], approve=False)

    request.refresh_from_db()
    risk.assessment.refresh_from_db()
    assert request.state == ApprovalState.REJECTED
    assert request.decided_by == users["rm2"]
    assert risk.assessment.category == RiskCategory.IS_RISIKO


def test_m_04_a_decided_request_cannot_be_decided_again(
    make_risk: MakeRisk, users: dict[str, User], make_user
) -> None:
    risk = make_risk(RiskStatus.SCORED)
    reclassify(risk, users["rm"], **IT_CLASSIFICATION)
    request = risk.approval_requests.get()
    decide(request, users["rm2"], approve=False)
    with pytest.raises(ValidationError):
        decide(request, users["rm2"], approve=True)


def test_m_04_downgrade_of_escalated_risk_needs_approval(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.ESCALATED, probability=4, impact=5)

    score(risk, users["rm"], probability=3, impact=5)

    risk.refresh_from_db()
    assert risk.assessment.score == 20  # unchanged until approved
    request = risk.approval_requests.get()
    assert request.kind == ApprovalKind.SCORE_DOWNGRADE
    assert (request.proposed_probability, request.proposed_impact) == (3, 5)

    decide(request, users["rm2"], approve=True)

    risk.refresh_from_db()
    assert risk.assessment.score == 15
    # An escalation is not withdrawn silently: it ends with documented incident response only
    assert risk.status == RiskStatus.ESCALATED


def test_m_04_upgrade_takes_effect_immediately(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(RiskStatus.ESCALATED, probability=4, impact=5)
    score(risk, users["rm"], probability=5, impact=5)
    risk.refresh_from_db()
    assert risk.assessment.score == 25
    assert not risk.approval_requests.exists()


def test_m_04_reclassification_to_is_takes_effect_immediately(
    make_risk: MakeRisk, users: dict[str, User], asset
) -> None:
    risk = make_risk(RiskStatus.SCORED, category=RiskCategory.IT_RISIKO, probability=5, impact=5)

    reclassify(
        risk,
        users["rm"],
        confidentiality=True,
        integrity=False,
        availability=True,
        origin=Origin.DELIBERATE_ATTACK,
        assets=[asset],
    )

    risk.refresh_from_db()
    assert risk.assessment.category == RiskCategory.IS_RISIKO
    assert risk.status == RiskStatus.ESCALATED  # 25 as IS risk


def test_m_04_reclassification_to_is_withdraws_pending_it_request(
    make_risk: MakeRisk, users: dict[str, User], asset
) -> None:
    risk = make_risk(RiskStatus.SCORED)
    reclassify(risk, users["rm"], **IT_CLASSIFICATION)
    reclassify(
        risk,
        users["rm2"],
        confidentiality=True,
        integrity=False,
        availability=False,
        origin=Origin.HUMAN_ERROR,
        assets=[asset],
    )
    request = risk.approval_requests.get()
    assert request.state == ApprovalState.WITHDRAWN
