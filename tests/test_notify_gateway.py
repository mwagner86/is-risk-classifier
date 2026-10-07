"""Iteration 6: the notify-gateway service (stand-in for the external e-mail/SMS provider) and
the HttpGateway that talks to it. Failures map to AK-03.3: timeout and HTTP 5xx."""

import http.client
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
import yaml

from apps.notifications.gateway import (
    GatewayError,
    GatewayServerError,
    GatewayTimeoutError,
    HttpGateway,
    OutgoingMessage,
)
from notify_gateway.messages import Message
from notify_gateway.server import MAX_BODY_BYTES, make_server

ROOT = Path(__file__).resolve().parent.parent
TOKEN = "gateway-test-token"
EMAIL = OutgoingMessage("EMAIL", "ir-team@example.org", "Eskalation: IS-Risiko 1", "Kennung: 1")
SMS = OutgoingMessage("SMS", "+49 30 1234567", "Eskalation: IS-Risiko 1", "Kennung: 1")


@dataclass
class Gateway:
    url: str
    delivered: list[Message] = field(default_factory=list)
    mode: list[str] = field(default_factory=lambda: ["none"])


@pytest.fixture
def gateway_server() -> Iterator[Gateway]:
    state = Gateway(url="")
    server = make_server(
        "127.0.0.1",
        0,
        token=TOKEN,
        deliver=state.delivered.append,
        failure_mode=lambda: state.mode[0],
        timeout_delay=1.5,
    )
    state.url = f"http://127.0.0.1:{server.server_address[1]}"
    thread = threading.Thread(
        target=server.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    yield state
    server.shutdown()
    server.server_close()


def _post(url: str, payload: Any, token: str | None = TOKEN) -> int:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(  # noqa: S310 - local test server
        url, data=json.dumps(payload).encode(), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=5) as response:  # noqa: S310
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return exc.code


def _payload(**overrides: str) -> dict[str, str]:
    return {**EMAIL.__dict__, **overrides}


# --- the gateway service --------------------------------------------------------------------


def test_gateway_accepts_e_mail_and_sms(gateway_server: Gateway) -> None:
    assert _post(f"{gateway_server.url}/messages", _payload()) == 202
    assert _post(f"{gateway_server.url}/messages", SMS.__dict__) == 202
    assert [m.channel for m in gateway_server.delivered] == ["EMAIL", "SMS"]


@pytest.mark.parametrize("token", [None, "wrong-token"])
def test_gateway_requires_the_token(gateway_server: Gateway, token: str | None) -> None:
    assert _post(f"{gateway_server.url}/messages", _payload(), token=token) == 401
    assert gateway_server.delivered == []


@pytest.mark.parametrize(
    "overrides",
    [
        {"channel": "FAX"},
        {"recipient": "keine-adresse"},
        {"channel": "SMS", "recipient": "ir-team@example.org"},
        {"subject": "x" * 201},
        {"body": "x" * 2001},
        {"subject": "Zeile\r\nBcc: alle@example.org"},
    ],
)
def test_gateway_rejects_invalid_messages(
    gateway_server: Gateway, overrides: dict[str, str]
) -> None:
    assert _post(f"{gateway_server.url}/messages", _payload(**overrides)) == 400
    assert gateway_server.delivered == []


def test_gateway_rejects_oversized_requests_unread(gateway_server: Gateway) -> None:
    host, port = gateway_server.url.removeprefix("http://").split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=5)
    connection.putrequest("POST", "/messages")
    connection.putheader("Authorization", f"Bearer {TOKEN}")
    connection.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
    connection.endheaders()
    assert connection.getresponse().status == 413
    connection.close()


@pytest.mark.req("AK-03.3")
def test_ak_03_3_gateway_answers_5xx_in_failure_mode(gateway_server: Gateway) -> None:
    gateway_server.mode[0] = "5xx"
    assert _post(f"{gateway_server.url}/messages", _payload()) == 503
    assert gateway_server.delivered == []


@pytest.mark.req("AK-03.3")
def test_ak_03_3_gateway_stalls_in_timeout_mode(gateway_server: Gateway) -> None:
    gateway_server.mode[0] = "timeout"
    started = time.monotonic()
    request = urllib.request.Request(  # noqa: S310 - local test server
        f"{gateway_server.url}/messages",
        data=json.dumps(_payload()).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with pytest.raises(TimeoutError):
        urllib.request.urlopen(request, timeout=0.3)  # noqa: S310
    assert time.monotonic() - started < 1.5
    assert gateway_server.delivered == []


def test_gateway_does_not_load_django_or_database_drivers() -> None:
    code = (
        "import sys, notify_gateway.server; "
        "print(sorted({m.split('.')[0] for m in sys.modules} & "
        "{'django', 'psycopg', 'apps', 'config'}))"
    )
    result = subprocess.run(  # noqa: S603 - fixed command
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT / "src"
    )
    assert result.stdout.strip() == "[]"


def test_gateway_and_mailpit_are_isolated_in_compose() -> None:
    compose = yaml.safe_load((ROOT / "compose.yaml").read_text())
    services, networks = compose["services"], compose["networks"]
    gateway = services["notify-gateway"]

    assert "env_file" not in gateway
    assert not any(
        k.startswith(("POSTGRES", "DATABASE", "OIDC", "DJANGO")) for k in gateway["environment"]
    )
    assert gateway["networks"] == ["notify"]
    assert gateway["read_only"] is True and gateway["cap_drop"] == ["ALL"]
    assert "ports" not in gateway
    assert networks["notify"]["internal"] is True
    assert "notify" in services["worker"]["networks"]
    for name in ("web", "db", "pdf-renderer"):
        assert "notify" not in services[name]["networks"], name
    assert all(p.startswith("127.0.0.1:") for p in services["mailpit"]["ports"])


# --- HttpGateway (the client in the worker) -------------------------------------------------


@pytest.fixture
def http_gateway(gateway_server: Gateway, settings) -> Callable[[], HttpGateway]:
    settings.NOTIFY_GATEWAY_URL = f"{gateway_server.url}/messages"
    settings.NOTIFY_GATEWAY_TOKEN = TOKEN
    settings.NOTIFY_GATEWAY_TIMEOUT = 0.5
    return HttpGateway


def test_http_gateway_delivers(
    gateway_server: Gateway, http_gateway: Callable[[], HttpGateway]
) -> None:
    http_gateway().send(EMAIL)
    assert [(m.recipient, m.subject) for m in gateway_server.delivered] == [
        (EMAIL.recipient, EMAIL.subject)
    ]


@pytest.mark.req("AK-03.3")
def test_ak_03_3_http_gateway_reports_5xx(
    gateway_server: Gateway, http_gateway: Callable[[], HttpGateway]
) -> None:
    gateway_server.mode[0] = "5xx"
    with pytest.raises(GatewayServerError) as excinfo:
        http_gateway().send(EMAIL)
    assert excinfo.value.status == 503


@pytest.mark.req("AK-03.3")
def test_ak_03_3_http_gateway_reports_timeout(
    gateway_server: Gateway, http_gateway: Callable[[], HttpGateway]
) -> None:
    gateway_server.mode[0] = "timeout"
    with pytest.raises(GatewayTimeoutError):
        http_gateway().send(EMAIL)


def test_http_gateway_reports_rejection_and_unreachable_gateway(
    gateway_server: Gateway, http_gateway: Callable[[], HttpGateway], settings
) -> None:
    settings.NOTIFY_GATEWAY_TOKEN = "falsch"
    with pytest.raises(GatewayError, match="401"):
        http_gateway().send(EMAIL)
    settings.NOTIFY_GATEWAY_URL = "http://127.0.0.1:9/messages"
    with pytest.raises(GatewayError, match="unreachable"):
        http_gateway().send(EMAIL)
