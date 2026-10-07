"""M-03: the PDF is produced in its own process without database access."""

import http.client
import json
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import yaml

from pdf_renderer.server import MAX_BODY_BYTES, make_server

pytestmark = pytest.mark.req("M-03")

ROOT = Path(__file__).resolve().parent.parent
FORBIDDEN_ENV = ("POSTGRES", "DATABASE", "SECRET", "OIDC", "PASSWORD")


def _compose() -> dict[str, Any]:
    compose: dict[str, Any] = yaml.safe_load((ROOT / "compose.yaml").read_text())
    return compose


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "exported_by": "Rita Müller (rm.mueller)",
        "exported_at": "07.10.2026 09:00",
        "filter": "Status: Bewertet",
        "risks": [
            {
                "id": "1b4e28ba-2fa1-11d2-883f-0016d3cca427",
                "title": "Test",
                "description": "Beschreibung",
                "category": "IS-Risiko",
                "status": "Bewertet",
                "goals": "Vertraulichkeit",
                "origin": "Unbekannt",
                "probability": 2,
                "impact": 3,
                "score": 6,
                "level": "mittel",
                "assets": "CI-0001 ERP",
                "created_at": "07.10.2026 08:00",
            }
        ],
    }
    payload.update(overrides)
    return payload


def test_m_03_renderer_does_not_load_django_or_database_drivers() -> None:
    code = (
        "import sys, pdf_renderer.server, pdf_renderer.render; "
        "print(sorted({m.split('.')[0] for m in sys.modules} & "
        "{'django', 'psycopg', 'psycopg2', 'apps', 'config'}))"
    )
    result = subprocess.run(  # noqa: S603 - fixed command, no user input
        [sys.executable, "-c", code], capture_output=True, text=True, check=True, cwd=ROOT / "src"
    )
    assert result.stdout.strip() == "[]"


def test_m_03_renderer_container_has_no_route_and_no_credentials_for_the_database() -> None:
    compose = _compose()
    renderer = compose["services"]["pdf-renderer"]

    assert "env_file" not in renderer
    assert not any(key.startswith(FORBIDDEN_ENV) for key in renderer.get("environment", {}))
    assert renderer["networks"] == ["pdf"]
    assert compose["networks"]["pdf"]["internal"] is True
    assert "pdf" not in compose["services"]["db"]["networks"]
    assert "pdf" in compose["services"]["web"]["networks"]


def test_m_03_renderer_container_is_locked_down() -> None:
    renderer = _compose()["services"]["pdf-renderer"]
    assert renderer["read_only"] is True
    assert renderer["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in renderer["security_opt"]
    assert "ports" not in renderer


@pytest.fixture
def server_url() -> Iterator[str]:
    server = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def _post(url: str, body: bytes, content_type: str = "application/json") -> tuple[int, bytes]:
    request = urllib.request.Request(  # noqa: S310 - local test server
        url, data=body, method="POST", headers={"Content-Type": content_type}
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def test_m_03_server_renders_a_valid_request(server_url: str) -> None:
    status, body = _post(f"{server_url}/render", json.dumps(_payload()).encode())
    assert status == 200
    assert body.startswith(b"%PDF-")


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b"kein json", 400),
        (json.dumps({"risks": "nein"}).encode(), 400),
        (json.dumps(_payload(exported_by="")).encode(), 400),
        (json.dumps(_payload(risks=[{"title": 5}])).encode(), 400),
    ],
)
def test_m_03_server_rejects_malformed_input(server_url: str, body: bytes, expected: int) -> None:
    assert _post(f"{server_url}/render", body)[0] == expected


def test_m_03_server_rejects_oversized_bodies_before_reading_them(server_url: str) -> None:
    host, port = server_url.removeprefix("http://").split(":")
    connection = http.client.HTTPConnection(host, int(port), timeout=10)
    connection.putrequest("POST", "/render")
    connection.putheader("Content-Type", "application/json")
    connection.putheader("Content-Length", str(MAX_BODY_BYTES + 1))
    connection.endheaders()  # announce the size, send nothing
    assert connection.getresponse().status == 413
    connection.close()


def test_m_03_server_answers_only_known_routes(server_url: str) -> None:
    assert _post(f"{server_url}/anything", b"{}")[0] == 404
    with urllib.request.urlopen(f"{server_url}/healthz", timeout=5) as response:  # noqa: S310
        assert response.status == 200
