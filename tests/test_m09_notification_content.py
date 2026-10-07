"""M-09: escalations carry only the identifier and a link that needs a login."""

from urllib.parse import urlparse

import pytest
from django.test import Client

from apps.accounts.models import User
from apps.notifications.gateway import OutgoingMessage
from apps.notifications.services import process_outbox
from apps.risks.models import RiskStatus
from apps.risks.services import score
from tests.conftest import MakeRisk

pytestmark = [pytest.mark.req("M-09"), pytest.mark.django_db]


def test_m_09_escalation_contains_only_identifier_and_link(
    make_risk: MakeRisk, users: dict[str, User], sent_messages: list[OutgoingMessage]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    risk.title = "Geheimer Titel"
    risk.description = "Vertrauliche Beschreibung"
    risk.save()
    score(risk, users["rm"], probability=5, impact=4)
    process_outbox()

    asset_name = risk.assessment.assets.get().name
    for message in sent_messages:
        text = f"{message.subject}\n{message.body}"
        assert str(risk.pk) in text
        assert f"http://testserver/risiken/{risk.pk}/" in text
        for secret in ("Geheimer Titel", "Vertrauliche Beschreibung", asset_name):
            assert secret not in text


def test_m_09_link_leads_to_login_first(
    make_risk: MakeRisk,
    users: dict[str, User],
    sent_messages: list[OutgoingMessage],
    client: Client,
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    score(risk, users["rm"], probability=5, impact=4)
    process_outbox()
    path = urlparse(sent_messages[0].body.split()[-1]).path

    response = client.get(path)

    assert response.status_code == 302
    assert response["Location"].startswith("/oidc/authenticate/")
    client.force_login(users["ciso"])
    assert client.get(path).status_code == 200
