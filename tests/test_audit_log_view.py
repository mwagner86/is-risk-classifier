"""Audit log page (iteration 4): readable for risk managers, CISO and administration."""

import pytest
from django.test import Client

from apps.accounts.models import Role, User
from apps.audit.models import AuditAction
from apps.risks.models import RiskStatus
from apps.risks.services import score
from tests.conftest import MakeRisk

pytestmark = pytest.mark.django_db


@pytest.mark.req("M-06")
@pytest.mark.parametrize("role", [Role.RISK_MANAGER, Role.CISO, Role.ADMIN])
def test_m_06_audit_log_is_readable_for_oversight_roles(
    role: Role, client: Client, make_user, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    score(risk, users["rm"], probability=2, impact=4)
    client.force_login(make_user(role))

    html = client.get("/audit-log/").content.decode()

    assert "Wert geändert" in html
    assert "probability" in html or "Eintrittswahrscheinlichkeit" in html
    assert users["rm"].username in html


@pytest.mark.req("M-05")
def test_m_05_reporters_do_not_see_the_audit_log(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["nutzer"])
    assert client.get("/audit-log/").status_code == 403


@pytest.mark.req("M-06")
def test_m_06_audit_log_page_is_read_only(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["rm"])
    assert client.post("/audit-log/").status_code == 405


@pytest.mark.req("M-06")
def test_m_06_audit_log_filters_by_action_and_risk(
    client: Client, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    first = make_risk(RiskStatus.CATEGORIZED)
    second = make_risk(RiskStatus.CATEGORIZED)
    score(first, users["rm"], probability=2, impact=4)
    score(second, users["rm"], probability=3, impact=3)
    client.force_login(users["ciso"])

    by_risk = client.get(f"/audit-log/?risk={first.pk}").content.decode()
    by_action = client.get(f"/audit-log/?action={AuditAction.STATUS_CHANGED}").content.decode()

    assert f"/risiken/{first.pk}/" in by_risk and f"/risiken/{second.pk}/" not in by_risk
    assert "Status geändert" in by_action and "Wert geändert</td>" not in by_action


def test_audit_log_is_paginated(
    client: Client, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    for _ in range(30):
        risk = make_risk(RiskStatus.CATEGORIZED)
        score(risk, users["rm"], probability=1, impact=1)  # 3 entries each
    client.force_login(users["rm"])
    first = client.get("/audit-log/").content.decode()
    assert first.count('class="audit-row"') == 50
    assert "Seite 1 von 2" in first


@pytest.mark.req("M-06")
def test_m_06_risk_detail_shows_its_history_to_oversight_only(
    client: Client, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED, reporter=users["nutzer"])
    score(risk, users["rm"], probability=2, impact=4)

    client.force_login(users["rm"])
    assert "Verlauf" in client.get(f"/risiken/{risk.pk}/").content.decode()
    client.force_login(users["nutzer"])
    assert "Verlauf" not in client.get(f"/risiken/{risk.pk}/").content.decode()


def test_audit_log_shows_german_labels_for_raw_values(
    client: Client, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    score(risk, users["rm"], probability=2, impact=4)
    client.force_login(users["rm"])
    html = client.get(f"/audit-log/?risk={risk.pk}").content.decode()
    assert "Kategorisiert" in html and "Bewertet" in html
    assert ">SCORED<" not in html
