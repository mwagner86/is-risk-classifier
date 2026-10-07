"""The boundary to the e-mail/SMS gateway.

``HttpGateway`` talks to the notify-gateway service (the stand-in for the external provider) and
is what the worker uses in the stack. ``MockGateway`` sends nothing, keeps the accepted messages
and simulates the failures of AK-03.3 via ``NOTIFY_MOCK_MODE`` (``ok``, ``timeout``, ``5xx``);
it is the default for tests. Both implement ``NotificationGateway``.
"""

import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
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


class HttpGateway:
    """POST each message to the gateway; map its failures to the errors of AK-03.3."""

    def send(self, message: OutgoingMessage) -> None:
        request = urllib.request.Request(  # noqa: S310 - fixed http URL from settings
            settings.NOTIFY_GATEWAY_URL,
            data=json.dumps(asdict(message)).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {settings.NOTIFY_GATEWAY_TOKEN}",
            },
            method="POST",
        )
        timeout = settings.NOTIFY_GATEWAY_TIMEOUT
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
                response.read()
        except urllib.error.HTTPError as exc:  # before URLError: it is a subclass
            if exc.code >= 500:
                raise GatewayServerError(exc.code) from exc
            raise GatewayError(f"gateway rejected the message with HTTP {exc.code}") from exc
        except TimeoutError as exc:
            raise GatewayTimeoutError from exc
        except urllib.error.URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise GatewayTimeoutError from exc
            raise GatewayError(f"gateway unreachable: {exc.reason}") from exc


def get_gateway() -> NotificationGateway:
    gateway: NotificationGateway = import_string(settings.NOTIFICATION_GATEWAY)()
    return gateway
