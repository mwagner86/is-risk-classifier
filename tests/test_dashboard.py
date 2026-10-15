"""Dashboard (iteration 3): key figures, 5 x 5 risk matrix, risk levels and the red flag of
AK-03.3 / decision 7."""

import re

import pytest
from django.core.exceptions import PermissionDenied
from django.test import Client

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditEntry
from apps.notifications.services import process_outbox, resend_failed
from apps.risks.dashboard import dashboard_data
from apps.risks.levels import RiskLevel, level_for
from apps.risks.models import RiskCategory, RiskStatus
from apps.risks.services import has_failed_notification, score
from tests.conftest import MakeRisk

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("gateway")]

FLAG_TEXT = "Notifikation fehlgeschlagen"


def _failed_escalation(make_risk: MakeRisk, users: dict[str, User], settings):
    settings.NOTIFY_MOCK_MODE = "timeout"
    risk = make_risk(RiskStatus.CATEGORIZED)
    score(risk, users["rm"], probability=5, impact=5)
    process_outbox()
    return risk


@pytest.mark.parametrize(
    ("value", "level"),
    [
        (25, RiskLevel.CRITICAL),
        (20, RiskLevel.CRITICAL),
        (19, RiskLevel.HIGH),
        (12, RiskLevel.HIGH),
        (11, RiskLevel.MEDIUM),
        (6, RiskLevel.MEDIUM),
        (5, RiskLevel.LOW),
        (1, RiskLevel.LOW),
        (None, None),
    ],
)
def test_risk_levels_follow_the_threat_model_bands(
    value: int | None, level: RiskLevel | None
) -> None:
    assert level_for(value) == level


def test_key_figures_count_open_risks_only(make_risk: MakeRisk, users: dict[str, User]) -> None:
    make_risk(RiskStatus.DRAFT)
    make_risk(RiskStatus.CLOSED)
    make_risk(RiskStatus.OBSOLETE)
    make_risk(RiskStatus.CATEGORIZED)
    make_risk(RiskStatus.SCORED, category=RiskCategory.IT_RISIKO)
    make_risk(RiskStatus.ESCALATED, probability=5, impact=4)
    make_risk(RiskStatus.VALIDATED)

    data = dashboard_data(users["rm"])

    assert data.open_count == 4
    assert (data.is_count, data.it_count) == (3, 1)
    assert data.escalated_count == 1
    assert data.failed_count == 0


@pytest.mark.req("M-10")
def test_m_10_key_figures_respect_visibility(
    make_risk: MakeRisk, users: dict[str, User], make_user
) -> None:
    make_risk(RiskStatus.SCORED, reporter=users["nutzer"])
    make_risk(RiskStatus.SCORED, reporter=make_user(Role.NUTZER))
    assert dashboard_data(users["nutzer"]).open_count == 1
    assert dashboard_data(users["ciso"]).open_count == 2


def test_matrix_counts_open_scored_risks_per_cell(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    make_risk(RiskStatus.ESCALATED, probability=4, impact=5)
    make_risk(RiskStatus.SCORED, category=RiskCategory.IT_RISIKO, probability=4, impact=5)
    make_risk(RiskStatus.VALIDATED, probability=1, impact=2)
    make_risk(RiskStatus.CLOSED, probability=4, impact=5)  # not open

    matrix = dashboard_data(users["rm"]).matrix

    # Rows from P = 5 at the top to P = 1, columns I = 1 to 5
    assert [row.probability for row in matrix] == [5, 4, 3, 2, 1]
    cell = matrix[1].cells[4]
    assert (cell.probability, cell.impact, cell.count, cell.level) == (4, 5, 2, RiskLevel.CRITICAL)
    assert matrix[4].cells[1].count == 1
    assert sum(c.count for row in matrix for c in row.cells) == 3


@pytest.mark.req("AK-03.3")
@pytest.mark.parametrize("role_key", ["rm", "ciso", "admin"])
def test_ak_03_3_failed_risk_is_highlighted_on_the_dashboard(
    role_key: str, make_risk: MakeRisk, users: dict[str, User], settings, client: Client
) -> None:
    risk = _failed_escalation(make_risk, users, settings)
    client.force_login(users[role_key])

    html = client.get("/").content.decode()

    row = re.search(r'<tr[^>]*class="[^"]*risk-failed[^"]*"[^>]*>.*?</tr>', html, re.S)
    assert row, "no highlighted row"
    assert f"/risiken/{risk.pk}/" in row.group(0)
    assert FLAG_TEXT in row.group(0)
    # Not by colour alone: an icon with a text alternative as well
    assert 'role="img"' in row.group(0)


@pytest.mark.req("AK-03.3")
def test_ak_03_3_reporter_dashboard_shows_no_admin_flag(
    make_risk: MakeRisk, users: dict[str, User], settings, client: Client
) -> None:
    _failed_escalation(make_risk, users, settings)
    client.force_login(users["nutzer"])
    assert "risk-failed" not in client.get("/").content.decode()


@pytest.mark.req("AK-03.3")
def test_decision_7_flag_stays_until_a_redelivery_succeeds(
    make_risk: MakeRisk, users: dict[str, User], settings
) -> None:
    risk = _failed_escalation(make_risk, users, settings)

    resend_failed(risk, users["admin"])
    process_outbox()  # gateway still down
    assert has_failed_notification(risk)

    settings.NOTIFY_MOCK_MODE = "ok"
    resend_failed(risk, users["admin"])
    process_outbox()

    assert not has_failed_notification(risk)
    # The audit trail keeps every failure
    failures = AuditEntry.objects.filter(risk=risk, action=AuditAction.NOTIFICATION_FAILED)
    assert failures.count() == 4
    assert AuditEntry.objects.filter(risk=risk, action=AuditAction.NOTIFICATION_RESENT).count() == 4


def test_decision_7_resend_does_not_duplicate_pending_copies(
    make_risk: MakeRisk, users: dict[str, User], settings
) -> None:
    risk = _failed_escalation(make_risk, users, settings)
    resend_failed(risk, users["admin"])
    resend_failed(risk, users["admin"])
    assert risk.notifications.filter(status="PENDING").count() == 2


@pytest.mark.req("M-05")
@pytest.mark.parametrize("role_key", ["nutzer", "rm", "ciso"])
def test_m_05_only_administration_resends(
    role_key: str, make_risk: MakeRisk, users: dict[str, User], settings, client: Client
) -> None:
    risk = _failed_escalation(make_risk, users, settings)
    with pytest.raises(PermissionDenied):
        resend_failed(risk, users[role_key])
    client.force_login(users[role_key])
    assert client.post(f"/eskalationen/{risk.pk}/erneut-senden/").status_code == 403


def test_admin_resends_from_the_escalation_page(
    make_risk: MakeRisk, users: dict[str, User], settings, client: Client
) -> None:
    risk = _failed_escalation(make_risk, users, settings)
    client.force_login(users["admin"])
    page = client.get("/eskalationen/").content.decode()
    assert f"/eskalationen/{risk.pk}/erneut-senden/" in page

    response = client.post(f"/eskalationen/{risk.pk}/erneut-senden/")

    assert response.status_code == 302
    assert risk.notifications.filter(status="PENDING").count() == 2
