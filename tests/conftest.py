from collections.abc import Callable

import pytest

from apps.accounts.models import Role, User
from apps.cmdb.models import Asset
from apps.notifications.gateway import MockGateway, OutgoingMessage
from apps.risks.models import CIATriad, Origin, Risk, RiskAssessment, RiskCategory, RiskStatus

MakeUser = Callable[..., User]
MakeRisk = Callable[..., Risk]

IR_EMAIL = "ir-team@example.org"
IR_PHONE = "+49 30 1234567"
IT_OPS_EMAIL = "it-ops@example.org"


@pytest.fixture(autouse=True)
def notification_settings(settings) -> None:
    settings.IR_TEAM_EMAILS = [IR_EMAIL]
    settings.IR_TEAM_PHONES = [IR_PHONE]
    settings.IT_OPS_EMAIL = IT_OPS_EMAIL
    settings.NOTIFY_MOCK_MODE = "ok"
    settings.APP_BASE_URL = "http://testserver"


@pytest.fixture(autouse=True)
def sent_messages() -> list[OutgoingMessage]:
    """Messages the mock gateway accepted during the test."""
    MockGateway.sent.clear()
    return MockGateway.sent


@pytest.fixture
def make_user(db: None) -> MakeUser:
    counter = iter(range(1, 10_000))

    def factory(role: Role, username: str | None = None) -> User:
        name = username or f"{role.lower()}-{next(counter)}"
        user: User = User.objects.create_user(username=name, role=role, oidc_subject=name)
        return user

    return factory


@pytest.fixture
def users(make_user: MakeUser) -> dict[str, User]:
    return {
        "nutzer": make_user(Role.NUTZER, "melder"),
        "rm": make_user(Role.RISK_MANAGER, "rm.mueller"),
        "rm2": make_user(Role.RISK_MANAGER, "rm.schmidt"),
        "ciso": make_user(Role.CISO, "ciso"),
        "admin": make_user(Role.ADMIN, "app-admin"),
    }


@pytest.fixture
def asset(db: None) -> Asset:
    asset: Asset = Asset.objects.create(cmdb_key="CI-T1", name="Testsystem", criticality=3)
    return asset


@pytest.fixture
def make_risk(users: dict[str, User], asset: Asset) -> MakeRisk:
    """Create a risk directly in ``status`` with data that satisfies that status' guards.

    Bypasses the state machine on purpose: tests of a single transition need an arbitrary
    starting point.
    """

    def factory(
        status: RiskStatus = RiskStatus.DRAFT,
        *,
        category: RiskCategory = RiskCategory.IS_RISIKO,
        probability: int | None = 2,
        impact: int | None = 3,
        reporter: User | None = None,
        incident_response: str = "",
    ) -> Risk:
        risk: Risk = Risk.objects.create(
            title="Testrisiko",
            description="Beschreibung",
            status=status,
            reporter=reporter or users["nutzer"],
            incident_response=incident_response,
        )
        scored = status not in (RiskStatus.DRAFT, RiskStatus.CATEGORIZED)
        assessment = RiskAssessment.objects.create(
            risk=risk,
            origin=Origin.DELIBERATE_ATTACK
            if category == RiskCategory.IS_RISIKO
            else Origin.TECHNICAL_FAILURE,
            # A DRAFT carries its category already: the submit step computes it before the
            # transition (US-01, iteration 2)
            category=category,
            probability=probability if scored else None,
            impact=impact if scored else None,
        )
        CIATriad.objects.create(
            assessment=assessment,
            confidentiality=category == RiskCategory.IS_RISIKO,
            availability=category == RiskCategory.IT_RISIKO,
        )
        assessment.assets.add(asset)
        return risk

    return factory
