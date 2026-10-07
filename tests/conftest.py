import threading
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from apps.accounts.models import Role, User
from apps.cmdb.models import Asset
from apps.notifications.gateway import MockGateway, OutgoingMessage
from apps.risks.models import CIATriad, Origin, Risk, RiskAssessment, RiskCategory, RiskStatus
from notify_gateway.server import make_server as make_gateway_server


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--trace-report", default=None, help="write requirement -> tests as Markdown to this file"
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    target = config.getoption("--trace-report")
    if not target:
        return
    tests: dict[str, set[str]] = {}
    for item in items:
        for marker in item.iter_markers("req"):
            tests.setdefault(marker.args[0], set()).add(item.nodeid.split("[")[0])
    lines = [
        "# Nachweis: Anforderung → Tests",
        "",
        "Erzeugt mit `make trace` aus den Markierungen `@pytest.mark.req(...)`.",
        "Nicht von Hand ändern.",
        "",
        "| Anforderung | Tests | Testfälle |",
        "| --- | --- | --- |",
    ]
    for req in sorted(tests):
        names = sorted(tests[req])
        cases = sum(1 for i in items if any(m.args[0] == req for m in i.iter_markers("req")))
        listing = "<br>".join(f"`{n}`" for n in names)
        lines.append(f"| {req} | {listing} | {cases} |")
    Path(target).write_text("\n".join(lines) + "\n", encoding="utf-8")


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
def _reset_mock_gateway() -> None:
    MockGateway.sent.clear()


@pytest.fixture(params=["mock", "http"])
def gateway(request: pytest.FixtureRequest, settings) -> Iterator[list[OutgoingMessage]]:
    """Run a test against the mock and against the real HTTP gateway (iteration 6).

    The HTTP variant starts the notify-gateway server in-process with a recording delivery
    instead of SMTP. NOTIFY_MOCK_MODE drives the failure mode of both, so the tests of
    iteration 2 run unchanged against either implementation. Yields the accepted messages.
    """
    if request.param == "mock":
        yield MockGateway.sent
        return
    delivered: list[OutgoingMessage] = []
    server = make_gateway_server(
        "127.0.0.1",
        0,
        token="test-token",
        deliver=lambda m: delivered.append(
            OutgoingMessage(
                channel=m.channel, recipient=m.recipient, subject=m.subject, body=m.body
            )
        ),
        failure_mode=lambda: {"ok": "none"}.get(
            settings.NOTIFY_MOCK_MODE, settings.NOTIFY_MOCK_MODE
        ),
        timeout_delay=0.6,
    )
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    settings.NOTIFICATION_GATEWAY = "apps.notifications.gateway.HttpGateway"
    settings.NOTIFY_GATEWAY_URL = f"http://127.0.0.1:{server.server_address[1]}/messages"
    settings.NOTIFY_GATEWAY_TOKEN = "test-token"
    settings.NOTIFY_GATEWAY_TIMEOUT = 0.2
    yield delivered
    server.shutdown()
    server.server_close()


@pytest.fixture
def sent_messages(gateway: list[OutgoingMessage]) -> list[OutgoingMessage]:
    """Messages the gateway accepted during the test (mock or HTTP, see ``gateway``)."""
    return gateway


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
