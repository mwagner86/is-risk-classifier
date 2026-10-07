"""Queue notifications (outbox) and deliver them through the gateway."""

import logging
from typing import TYPE_CHECKING

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditAction
from apps.audit.services import record
from apps.notifications.gateway import (
    GatewayError,
    NotificationGateway,
    OutgoingMessage,
    get_gateway,
)
from apps.notifications.models import Channel, Notification, NotificationKind, NotificationStatus

if TYPE_CHECKING:
    from apps.risks.models import Risk

logger = logging.getLogger(__name__)


def risk_link(risk: "Risk") -> str:
    return f"{settings.APP_BASE_URL.rstrip('/')}/risiken/{risk.pk}/"


def _queue(
    risk: "Risk",
    kind: NotificationKind,
    recipients: list[tuple[Channel, str]],
    subject: str,
    intro: str,
) -> list[Notification]:
    # M-09: identifier and link only; the link needs a login (M-05)
    body = f"{intro}\nKennung: {risk.pk}\nDetails nach Anmeldung: {risk_link(risk)}"
    return [
        Notification.objects.create(
            risk=risk, kind=kind, channel=channel, recipient=recipient, subject=subject, body=body
        )
        for channel, recipient in recipients
    ]


def enqueue_escalation(risk: "Risk") -> list[Notification]:
    recipients = [(Channel.EMAIL, address) for address in settings.IR_TEAM_EMAILS] + [
        (Channel.SMS, number) for number in settings.IR_TEAM_PHONES
    ]
    if not recipients:
        logger.error(
            "risk %s escalated but no incident response recipients are configured", risk.pk
        )
    return _queue(
        risk,
        NotificationKind.ESCALATION,
        recipients,
        subject=f"Eskalation: IS-Risiko {risk.pk}",
        intro="Ein IS-Risiko wurde eskaliert und erfordert sofortigen Handlungsbedarf.",
    )


def enqueue_it_handover(risk: "Risk") -> list[Notification]:
    if not settings.IT_OPS_EMAIL:
        logger.error("risk %s handed over but IT_OPS_EMAIL is not configured", risk.pk)
        return []
    return _queue(
        risk,
        NotificationKind.IT_OPS_HANDOVER,
        [(Channel.EMAIL, settings.IT_OPS_EMAIL)],
        subject=f"Weitergabe: IT-Risiko {risk.pk}",
        intro="Ein allgemeines IT-Risiko wurde an das IT-Operations-Management übergeben.",
    )


def process_outbox(*, gateway: NotificationGateway | None = None, batch_size: int = 50) -> int:
    """Send pending notifications; a failure is logged in the audit log (AK-03.3)."""
    gateway = gateway or get_gateway()
    with transaction.atomic():
        pending = list(
            Notification.objects.select_for_update(skip_locked=True)
            .select_related("risk")
            .filter(status=NotificationStatus.PENDING)
            .order_by("created_at")[:batch_size]
        )
        for notification in pending:
            notification.attempts += 1
            notification.dispatched_at = timezone.now()
            message = OutgoingMessage(
                channel=notification.channel,
                recipient=notification.recipient,
                subject=notification.subject,
                body=notification.body,
            )
            try:
                gateway.send(message)
            except GatewayError as exc:
                notification.status = NotificationStatus.FAILED
                notification.last_error = str(exc)
                record(
                    actor=None,
                    action=AuditAction.NOTIFICATION_FAILED,
                    obj=notification,
                    risk=notification.risk,
                    field="channel",
                    new=f"{notification.get_channel_display()} an {notification.recipient}: {exc}",
                )
                logger.warning("notification %s failed: %s", notification.pk, exc)
            else:
                notification.status = NotificationStatus.DELIVERED
            notification.save(update_fields=["attempts", "dispatched_at", "status", "last_error"])
    return len(pending)
