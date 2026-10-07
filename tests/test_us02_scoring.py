"""US-02: the risk manager quantifies P and I; the system computes R = P x I."""

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.models import User
from apps.risks.models import RiskCategory, RiskStatus
from apps.risks.services import score
from tests.conftest import MakeRisk

pytestmark = pytest.mark.django_db

RANGE_P = "Zulässiger Wertebereich für die Eintrittswahrscheinlichkeit ist 1 bis 5"
RANGE_I = "Zulässiger Wertebereich für das Schadensausmaß ist 1 bis 5"


@pytest.mark.req("AK-02.1")
def test_ak_02_1_score_is_the_product(make_risk: MakeRisk, users: dict[str, User]) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED, category=RiskCategory.IT_RISIKO)

    score(risk, users["rm"], probability=4, impact=5)

    risk.refresh_from_db()
    assert risk.assessment.score == 20
    assert risk.status == RiskStatus.SCORED


@pytest.mark.req("AK-02.2")
@pytest.mark.parametrize(
    ("probability", "impact", "field", "message"),
    [
        (3, 6, "impact", RANGE_I),
        (3, 0, "impact", RANGE_I),
        (6, 3, "probability", RANGE_P),
        (0, 3, "probability", RANGE_P),
        (-1, 3, "probability", RANGE_P),
    ],
)
def test_ak_02_2_value_out_of_range_is_rejected_naming_the_dimension(
    probability: int,
    impact: int,
    field: str,
    message: str,
    make_risk: MakeRisk,
    users: dict[str, User],
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)

    with pytest.raises(ValidationError) as excinfo:
        score(risk, users["rm"], probability=probability, impact=impact)

    assert excinfo.value.message_dict == {field: [message]}
    risk.refresh_from_db()
    assert risk.status == RiskStatus.CATEGORIZED
    assert risk.assessment.score is None


@pytest.mark.req("AK-02.3")
@pytest.mark.parametrize("value", ["Hoch", "", None, 2.5, "3", True])
def test_ak_02_3_non_integer_is_rejected_on_the_server(
    value: object, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)

    with pytest.raises(ValidationError) as excinfo:
        score(risk, users["rm"], probability=3, impact=value)

    assert excinfo.value.message_dict == {"impact": [RANGE_I]}
    risk.refresh_from_db()
    assert risk.assessment.score is None


@pytest.mark.req("M-05")
@pytest.mark.parametrize("role_key", ["nutzer", "ciso", "admin"])
def test_m_05_only_risk_managers_score(
    role_key: str, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    with pytest.raises(PermissionDenied):
        score(risk, users[role_key], probability=2, impact=2)


@pytest.mark.req("US-02")
@pytest.mark.parametrize(
    "status", [RiskStatus.DRAFT, RiskStatus.VALIDATED, RiskStatus.CLOSED, RiskStatus.OBSOLETE]
)
def test_us_02_scoring_only_while_the_assessment_is_open(
    status: RiskStatus, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(status)
    with pytest.raises(ValidationError):
        score(risk, users["rm"], probability=2, impact=2)
