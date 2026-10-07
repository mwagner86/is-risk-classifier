"""The boundary to the e-mail/SMS gateway.

Until iteration 6 only ``MockGateway`` exists: it sends nothing, keeps the accepted messages and
can simulate the failures of AK-03.3 via ``NOTIFY_MOCK_MODE`` (``ok``, ``timeout``, ``5xx``).
The real HTTP gateway will implement the same protocol.
"""

import logging
from dataclasses import dataclass
from typing import ClassVar, Protocol

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OutgoingMessage:
    channel: str
    recipient: str
    subject: str
    body: str


class GatewayError(Exception):
    """Delivery failed; the caller records it and flags the risk."""


class GatewayTimeoutError(GatewayError):
    def __init__(self) -> None:
        super().__init__("gateway timeout")


class GatewayServerError(GatewayError):
    def __init__(self, status: int) -> None:
        super().__init__(f"gateway returned HTTP {status}")
        self.status = status


class NotificationGateway(Protocol):
    def send(self, message: OutgoingMessage) -> None: ...


class MockGateway:
    sent: ClassVar[list[OutgoingMessage]] = []

    def send(self, message: OutgoingMessage) -> None:
        mode = settings.NOTIFY_MOCK_MODE
        if mode == "timeout":
            raise GatewayTimeoutError
        if mode == "5xx":
            raise GatewayServerError(503)
        if mode != "ok":
            raise ImproperlyConfigured(f"NOTIFY_MOCK_MODE must be ok, timeout or 5xx, not {mode!r}")
        self.sent.append(message)
        logger.info(
            "mock gateway accepted %s to %s: %s",
            message.channel,
            message.recipient,
            message.subject,
        )


def get_gateway() -> NotificationGateway:
    gateway: NotificationGateway = import_string(settings.NOTIFICATION_GATEWAY)()
    return gateway
