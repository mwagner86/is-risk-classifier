"""The UI is available in German (default, source language) and English; users switch in the
header, the choice is kept in a cookie."""

import csv
import gettext
import io
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest
from django.conf import settings
from django.test import Client
from pypdf import PdfReader

from apps.accounts.models import User
from apps.cmdb.models import Asset
from apps.exports import pdf_client
from apps.notifications.services import process_outbox
from apps.risks.models import Origin, RiskCategory, RiskStatus
from apps.risks.services import score
from pdf_renderer.render import render
from tests.conftest import MakeRisk

pytestmark = pytest.mark.django_db

LOCALE = Path(__file__).resolve().parent.parent / "src" / "locale" / "en" / "LC_MESSAGES"
# Words that must not survive in the English UI (umlauts are checked separately)
GERMAN = re.compile(
    r"\b(und|oder|nicht|keine?|Risiken|Speichern|Abmelden|Bewertung|Freigabe\w*|Eskalier\w*|"
    r"Erfass\w*|Ursprung|Schutzziel\w*|Zurück|Weiter|alle|Kennung|Verlauf|Aktion(en)?)\b"
)


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("script", "style", "code"):
            self._skip += 1
        for name, value in attrs:
            if name in ("aria-label", "title", "placeholder") and value:
                self.parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "code"):
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self.parts.append(data)


def visible_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return " ".join(" ".join(parser.parts).split())


@pytest.fixture
def english(client: Client) -> Client:
    client.post("/sprache/", {"language": "en", "next": "/"})
    return client


@pytest.fixture
def english_register(make_risk: MakeRisk, users: dict[str, User], settings) -> dict[str, Any]:
    """Risks with English data, one of them escalated with a failed notification."""
    asset = Asset.objects.create(cmdb_key="CI-EN", name="Payroll server", criticality=4)
    settings.NOTIFY_MOCK_MODE = "timeout"
    failed = make_risk(RiskStatus.CATEGORIZED)
    failed.title, failed.description = "Phishing campaign", "Credentials were phished"
    failed.save()
    failed.assessment.assets.set([asset])
    score(failed, users["rm"], probability=5, impact=5)
    process_outbox()
    other = make_risk(RiskStatus.SCORED, category=RiskCategory.IT_RISIKO, probability=2, impact=2)
    other.title, other.description = "Disk wear", "SMART warnings"
    other.save()
    return {"failed": failed, "other": other, "asset": asset}


def test_default_language_is_german(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["rm"])
    html = client.get("/").content.decode()
    assert '<html lang="de">' in html
    assert "Abmelden" in html


def test_switching_to_english_sets_a_cookie_and_returns_to_the_page(
    client: Client, users: dict[str, User]
) -> None:
    client.force_login(users["rm"])

    response = client.post("/sprache/", {"language": "en", "next": "/risiken/"})

    assert response.status_code == 302
    assert response["Location"] == "/risiken/"
    cookie = response.cookies[settings.LANGUAGE_COOKIE_NAME]
    assert cookie.value == "en"
    assert cookie["httponly"] and cookie["samesite"] == "Lax"
    html = client.get("/risiken/").content.decode()
    assert '<html lang="en">' in html
    assert "Sign out" in html and "Report risk" in html


def test_switch_is_offered_on_every_page_without_login(client: Client) -> None:
    html = client.get("/anmeldung-abgelehnt/").content.decode()
    form = re.search(r'<form action="/sprache/" method="post".*?</form>', html, re.S)
    assert form
    assert 'value="de"' in form.group(0) and 'value="en"' in form.group(0)
    assert 'aria-pressed="true"' in form.group(0)


def test_browser_language_is_used_without_a_choice(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["rm"])
    html = client.get("/", headers={"Accept-Language": "en-GB,en;q=0.9"}).content.decode()
    assert '<html lang="en">' in html


def test_switching_back_to_german(english: Client, users: dict[str, User]) -> None:
    english.force_login(users["rm"])
    english.post("/sprache/", {"language": "de", "next": "/"})
    assert '<html lang="de">' in english.get("/").content.decode()


def test_foreign_redirect_targets_are_ignored(client: Client) -> None:
    response = client.post("/sprache/", {"language": "en", "next": "https://evil.example/"})
    assert response["Location"] == "/"


@pytest.mark.parametrize(
    ("role_key", "path"),
    [
        ("rm", "/"),
        ("rm", "/risiken/"),
        ("rm", "/risiken/{failed}/"),
        ("rm", "/risiken/{other}/bewertung/"),
        ("rm", "/risiken/{failed}/klassifizierung/"),
        ("rm", "/freigaben/"),
        ("rm", "/export/?category=IS_RISIKO"),
        ("rm", "/audit-log/"),
        ("nutzer", "/risiken/neu/"),
        ("admin", "/eskalationen/"),
        ("ciso", "/assets/"),
        ("ciso", "/risiken/{failed}/incident-response/"),
    ],
)
def test_pages_contain_no_german_in_english(
    role_key: str,
    path: str,
    english: Client,
    users: dict[str, User],
    english_register: dict[str, Any],
) -> None:
    english.force_login(users[role_key])
    url = path.format(failed=english_register["failed"].pk, other=english_register["other"].pk)

    response = english.get(url)

    assert response.status_code == 200, url
    text = visible_text(response.content.decode())
    # Usernames of the fixtures and the risk identifiers are data, not UI text
    assert not re.search(r"[äöüÄÖÜß]", text), text
    leftover = GERMAN.search(text)
    assert leftover is None, leftover.group(0)


@pytest.mark.req("AK-01.3")
def test_ak_01_3_message_in_english(english: Client, users: dict[str, User], asset: Asset) -> None:
    english.force_login(users["nutzer"])
    html = english.post(
        "/risiken/neu/",
        {
            "title": "Leak",
            "description": "x",
            "confidentiality": "on",
            "assets": [asset.pk],
            "action": "submit",
        },
    ).content.decode()
    assert "The origin must be specified for the CIA classification" in html


@pytest.mark.req("AK-02.2")
def test_ak_02_2_message_in_english(
    english: Client, users: dict[str, User], make_risk: MakeRisk
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    english.force_login(users["rm"])
    html = english.post(
        f"/risiken/{risk.pk}/bewertung/", {"probability": 3, "impact": 6}
    ).content.decode()
    assert "The permitted range for the impact is 1 to 5" in html


@pytest.mark.req("M-08")
def test_m_08_csv_export_in_english(
    english: Client, users: dict[str, User], english_register: dict[str, Any]
) -> None:
    english.force_login(users["rm"])
    response = english.get("/export/csv/?category=IS_RISIKO")
    rows = list(csv.DictReader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[0]["Category"] == "IS risk"
    assert rows[0]["Risk level"] == "critical"
    assert rows[0]["Confidentiality"] == "yes"
    assert re.fullmatch(r"\d{4}-\d\d-\d\d \d\d:\d\d", rows[0]["Exported on"])


@pytest.mark.req("M-08")
def test_m_08_pdf_export_in_english(
    english: Client, users: dict[str, User], english_register: dict[str, Any], monkeypatch
) -> None:
    monkeypatch.setattr(pdf_client, "render_pdf", render)
    english.force_login(users["rm"])
    response = english.get("/export/pdf/?category=IS_RISIKO")
    text = "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)
    assert re.search(r"Exported by \S+ on \d{4}-\d\d-\d\d \d\d:\d\d", text)
    assert "Risk export" in text and "Category" in text
    assert "Kategorie" not in text


def test_keycloak_login_page_follows_the_language(english: Client) -> None:
    response = english.get("/oidc/authenticate/")
    query = parse_qs(urlparse(response["Location"]).query)
    assert query["ui_locales"] == ["en"]


def test_catalogue_is_complete_and_compiled() -> None:
    po = (LOCALE / "django.po").read_text(encoding="utf-8")
    assert "#, fuzzy" not in po
    entries = [e for e in po.split("\n\n")[1:] if "msgid" in e]
    for entry in entries:
        assert not re.search(r'^msgstr(\[\d\])? ""\Z', entry.strip().split("\n")[-1], re.M), entry
    # The compiled catalogue matches the source: every msgid resolves to its msgstr
    catalogue = gettext.GNUTranslations((LOCALE / "django.mo").open("rb"))
    single = re.findall(r'^msgid "(.+)"\nmsgstr "(.+)"$', po, re.M)
    assert single
    for msgid, msgstr in single:
        assert catalogue.gettext(msgid.replace('\\"', '"')) == msgstr.replace('\\"', '"')


def test_spec_messages_stay_literal_in_german() -> None:
    from django.utils import translation

    from apps.risks.services import ORIGIN_MISSING

    with translation.override("de"):
        assert (
            str(ORIGIN_MISSING) == "Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden"
        )
    with translation.override("en"):
        assert str(Origin.TECHNICAL_FAILURE.label) == "Technical failure / wear"
