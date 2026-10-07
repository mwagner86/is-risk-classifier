"""Hardening of the web layer (iteration 5, M-05): security headers, CSP without inline code,
no caching of authenticated pages, sessions that expire, deploy check in HTTPS mode."""

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client

from apps.accounts.models import User

pytestmark = [pytest.mark.req("M-05"), pytest.mark.django_db]

ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = ROOT / "src" / "templates"


def _csp(response) -> dict[str, str]:
    header = response["Content-Security-Policy"]
    return {d.split()[0]: " ".join(d.split()[1:]) for d in header.split(";") if d.strip()}


def test_m_05_content_security_policy_forbids_inline_code(
    client: Client, users: dict[str, User]
) -> None:
    client.force_login(users["rm"])
    csp = _csp(client.get("/"))

    assert csp["default-src"] == "'self'"
    assert csp["script-src"] == "'self'"
    assert csp["style-src"] == "'self'"
    assert csp["object-src"] == "'none'"
    assert csp["base-uri"] == "'none'"
    assert csp["frame-ancestors"] == "'none'"
    assert "unsafe" not in " ".join(csp.values())
    # The logout form redirects to the identity provider
    assert csp["form-action"] == f"'self' {settings.OIDC_PUBLIC_ORIGIN}"


def test_m_05_security_headers_on_every_response(client: Client) -> None:
    response = client.get("/healthz")
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["X-Frame-Options"] == "DENY"
    assert response["Referrer-Policy"] == "same-origin"
    assert response["Cross-Origin-Opener-Policy"] == "same-origin"
    assert "camera=()" in response["Permissions-Policy"]
    assert "Content-Security-Policy" in response


def test_m_05_authenticated_pages_are_not_cached(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["rm"])
    assert "no-store" in client.get("/risiken/")["Cache-Control"]


def test_m_05_templates_contain_no_inline_script_style_or_handlers() -> None:
    for template in TEMPLATES.rglob("*.html"):
        html = template.read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), template
        assert not re.search(r"<style\b", html), template
        assert not re.search(r"\sstyle=", html), template
        assert not re.search(r"\son[a-z]+=", html), template
        assert "hx-on" not in html, template


def test_m_05_htmx_runs_without_eval_and_without_injected_styles(
    client: Client, users: dict[str, User]
) -> None:
    client.force_login(users["rm"])
    meta = re.search(
        r'<meta name="htmx-config" content=\'([^\']+)\'>', client.get("/").content.decode()
    )
    assert meta
    assert '"allowEval":false' in meta.group(1).replace(" ", "")
    assert '"includeIndicatorStyles":false' in meta.group(1).replace(" ", "")


def test_m_05_sessions_expire() -> None:
    assert settings.SESSION_COOKIE_HTTPONLY is True
    assert settings.SESSION_COOKIE_SAMESITE == "Lax"
    assert settings.SESSION_COOKIE_AGE <= 8 * 60 * 60
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True


def test_m_05_deploy_check_passes_in_https_mode() -> None:
    env = {
        **os.environ,
        "DJANGO_DEBUG": "false",
        "DJANGO_HTTPS": "true",
        "DJANGO_SECRET_KEY": "x" * 64 + "-only-for-the-deploy-check-9f8e7d6c5b4a",
        "DJANGO_ALLOWED_HOSTS": "risk.example.org",
    }
    result = subprocess.run(
        [sys.executable, "src/manage.py", "check", "--deploy", "--fail-level", "WARNING"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        env=env,
    )
    assert result.returncode == 0, result.stdout + result.stderr
