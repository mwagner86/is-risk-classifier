"""US-03: an IS risk with R >= 20 is escalated asynchronously to the incident response team."""

import pytest

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditEntry
from apps.notifications.gateway import OutgoingMessage
from apps.notifications.models import Notification, NotificationKind, NotificationStatus
from apps.notifications.services import process_outbox
from apps.risks.models import RiskCategory, RiskStatus
from apps.risks.services import has_failed_notification, score
from apps.risks.state_machine import transition
from tests.conftest import IR_EMAIL, IR_PHONE, MakeRisk

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("gateway")]


@pytest.mark.req("AK-03.1")
def test_ak_03_1_is_risk_at_20_is_escalated_and_notified_asynchronously(
    make_risk: MakeRisk, users: dict[str, User], sent_messages: list[OutgoingMessage]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)

    score(risk, users["rm"], probability=4, impact=5)

    risk.refresh_from_db()
    assert risk.status == RiskStatus.ESCALATED
    queued = Notification.objects.filter(risk=risk, kind=NotificationKind.ESCALATION)
    # Asynchronous: queued with the status change, nothing sent yet
    assert {(n.channel, n.recipient) for n in queued} == {("EMAIL", IR_EMAIL), ("SMS", IR_PHONE)}
    assert all(n.status == NotificationStatus.PENDING for n in queued)
    assert sent_messages == []

    process_outbox()

    assert all(n.is_delivered for n in queued.all())
    assert sorted(m.recipient for m in sent_messages) == sorted([IR_EMAIL, IR_PHONE])


@pytest.mark.req("AK-03.1")
def test_ak_03_1_upgrade_in_scored_escalates_immediately(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.SCORED, probability=3, impact=5)

    score(risk, users["rm"], probability=4, impact=5)

    risk.refresh_from_db()
    assert risk.status == RiskStatus.ESCALATED


@pytest.mark.req("AK-03.2")
def test_ak_03_2_it_risk_at_25_is_never_escalated(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED, category=RiskCategory.IT_RISIKO)

    score(risk, users["rm"], probability=5, impact=5)

    risk.refresh_from_db()
    assert risk.status == RiskStatus.SCORED
    assert not Notification.objects.filter(kind=NotificationKind.ESCALATION).exists()
    transition(risk, RiskStatus.VALIDATED, users["rm"])
    assert risk.status == RiskStatus.VALIDATED


@pytest.mark.req("AK-03.3")
@pytest.mark.parametrize("mode", ["timeout", "5xx"])
def test_ak_03_3_gateway_failure_is_logged_and_flagged(
    mode: str, settings, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    settings.NOTIFY_MOCK_MODE = mode
    risk = make_risk(RiskStatus.CATEGORIZED)
    score(risk, users["rm"], probability=5, impact=5)

    process_outbox()

    risk.refresh_from_db()
    assert risk.status == RiskStatus.ESCALATED  # the escalation itself stands
    assert all(n.status == NotificationStatus.FAILED for n in risk.notifications.all())
    failures = AuditEntry.objects.filter(risk=risk, action=AuditAction.NOTIFICATION_FAILED)
    assert failures.count() == 2
    assert str(AuditAction.NOTIFICATION_FAILED.label) == "Notifikation fehlgeschlagen"
    # Language-neutral value: readable in the German and the English UI alike
    assert {e.new_value.split(":")[0] for e in failures} == {
        "EMAIL → ir-team@example.org",
        "SMS → +49 30 1234567",
    }
    assert has_failed_notification(risk)


@pytest.mark.req("AK-03.3")
def test_ak_03_3_successful_delivery_is_not_flagged(
    make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    score(risk, users["rm"], probability=5, impact=5)
    process_outbox()
    assert not has_failed_notification(risk)
