"""The web forms behind US-01 and US-02: what the user sees, and that the server decides."""

import re

import pytest
from django.test import Client

from apps.accounts.models import Role, User
from apps.cmdb.models import Asset
from apps.risks.models import ApprovalState, Origin, Risk, RiskCategory, RiskStatus
from tests.conftest import MakeRisk

pytestmark = pytest.mark.django_db

ORIGIN_MISSING = "Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden"


def _tag(html: str, name: str) -> str:
    """The opening tag of the form control called ``name``."""
    match = re.search(rf'<(?:input|select|textarea)[^>]*name="{name}"[^>]*>', html)
    assert match, f"no control named {name}"
    return match.group(0)


@pytest.fixture
def nutzer_client(client: Client, users: dict[str, User]) -> Client:
    client.force_login(users["nutzer"])
    return client


@pytest.fixture
def rm_client(client: Client, users: dict[str, User]) -> Client:
    client.force_login(users["rm"])
    return client


# --- US-01 ----------------------------------------------------------------------------------


@pytest.mark.req("AK-01.3")
def test_ak_01_3_form_blocks_saving_focuses_origin_and_shows_message(
    nutzer_client: Client, asset: Asset
) -> None:
    response = nutzer_client.post(
        "/risiken/neu/",
        {
            "title": "Datenabfluss",
            "description": "USB-Stick verloren",
            "confidentiality": "on",
            "origin": "",
            "assets": [asset.pk],
            "action": "submit",
        },
    )

    html = response.content.decode()
    assert response.status_code == 200
    assert ORIGIN_MISSING in html
    origin = _tag(html, "origin")
    assert "autofocus" in origin
    assert 'aria-invalid="true"' in origin
    assert "autofocus" not in _tag(html, "title")
    assert not Risk.objects.exists()


@pytest.mark.req("AK-01.1")
def test_ak_01_1_preview_unlocks_assets_for_is_risk(nutzer_client: Client, asset: Asset) -> None:
    response = nutzer_client.post(
        "/risiken/kategorie-vorschau/",
        {"integrity": "on", "origin": Origin.TECHNICAL_FAILURE},
        headers={"HX-Request": "true"},
    )
    html = response.content.decode()
    assert "IS-Risiko" in html
    assert "disabled" not in _tag(html, "assets")
    assert "required" in _tag(html, "assets")


@pytest.mark.req("AK-01.2")
def test_ak_01_2_preview_shows_it_risk_without_assets(nutzer_client: Client, asset: Asset) -> None:
    response = nutzer_client.post(
        "/risiken/kategorie-vorschau/",
        {"availability": "on", "origin": Origin.TECHNICAL_FAILURE},
        headers={"HX-Request": "true"},
    )
    html = response.content.decode()
    assert "Allgemeines IT-Risiko" in html
    assert "Freigabe" in html  # M-04: the user learns it is a request
    assert "disabled" in _tag(html, "assets")


@pytest.mark.req("US-01")
def test_us_01_capture_succeeds_and_redirects_to_detail(
    nutzer_client: Client, asset: Asset
) -> None:
    response = nutzer_client.post(
        "/risiken/neu/",
        {
            "title": "Datenabfluss",
            "description": "USB-Stick verloren",
            "confidentiality": "on",
            "origin": Origin.HUMAN_ERROR,
            "assets": [asset.pk],
            "action": "submit",
        },
    )
    risk = Risk.objects.get()
    assert response.status_code == 302
    assert response["Location"] == f"/risiken/{risk.pk}/"
    assert risk.status == RiskStatus.CATEGORIZED
    assert risk.assessment.category == RiskCategory.IS_RISIKO


@pytest.mark.req("US-01")
def test_us_01_draft_can_be_stored_incomplete(nutzer_client: Client) -> None:
    response = nutzer_client.post(
        "/risiken/neu/", {"title": "Noch unklar", "description": "", "action": "draft"}
    )
    risk = Risk.objects.get()
    assert response.status_code == 302
    assert risk.status == RiskStatus.DRAFT


# --- US-02 ----------------------------------------------------------------------------------


@pytest.mark.req("AK-02.2")
def test_ak_02_2_form_marks_field_and_names_dimension(
    rm_client: Client, make_risk: MakeRisk
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)

    response = rm_client.post(f"/risiken/{risk.pk}/bewertung/", {"probability": 3, "impact": 6})

    html = response.content.decode()
    assert response.status_code == 200
    assert "Zulässiger Wertebereich für das Schadensausmaß ist 1 bis 5" in html
    assert 'aria-invalid="true"' in _tag(html, "impact")
    assert 'aria-invalid="true"' not in _tag(html, "probability")
    risk.refresh_from_db()
    assert risk.assessment.score is None


@pytest.mark.req("AK-02.3")
def test_ak_02_3_letters_are_rejected_and_score_not_computable(
    rm_client: Client, make_risk: MakeRisk
) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)

    response = rm_client.post(
        f"/risiken/{risk.pk}/bewertung/", {"probability": "Hoch", "impact": 4}
    )

    html = response.content.decode()
    assert "Zulässiger Wertebereich für die Eintrittswahrscheinlichkeit ist 1 bis 5" in html
    assert "Nicht berechenbar" in html
    # The browser already refuses letters: numeric input limited to 1..5
    tag = _tag(html, "probability")
    for attribute in ('type="number"', 'min="1"', 'max="5"', 'step="1"'):
        assert attribute in tag


@pytest.mark.req("AK-02.3")
@pytest.mark.parametrize(
    ("probability", "impact", "expected"),
    [("4", "5", "20"), ("Hoch", "5", "Nicht berechenbar"), ("2", "6", "Nicht berechenbar")],
)
def test_ak_02_3_live_score_preview(
    probability: str, impact: str, expected: str, rm_client: Client
) -> None:
    response = rm_client.post(
        "/risiken/score-vorschau/",
        {"probability": probability, "impact": impact},
        headers={"HX-Request": "true"},
    )
    assert expected in response.content.decode()


@pytest.mark.req("AK-02.1")
def test_ak_02_1_form_saves_score(rm_client: Client, make_risk: MakeRisk) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED, category=RiskCategory.IT_RISIKO)
    response = rm_client.post(f"/risiken/{risk.pk}/bewertung/", {"probability": 4, "impact": 5})
    assert response.status_code == 302
    risk.refresh_from_db()
    assert risk.assessment.score == 20


# --- M-05: object-level visibility and actions ----------------------------------------------


@pytest.mark.req("M-05")
def test_m_05_reporter_sees_only_own_risks(
    client: Client, make_risk: MakeRisk, make_user, users: dict[str, User]
) -> None:
    other = make_user(Role.NUTZER)
    own = make_risk(RiskStatus.CATEGORIZED, reporter=users["nutzer"])
    foreign = make_risk(RiskStatus.CATEGORIZED, reporter=other)
    client.force_login(users["nutzer"])

    listing = client.get("/risiken/").content.decode()

    assert f"/risiken/{own.pk}/" in listing
    assert f"/risiken/{foreign.pk}/" not in listing
    assert client.get(f"/risiken/{foreign.pk}/").status_code == 404


@pytest.mark.req("M-05")
def test_m_05_reporter_cannot_open_scoring(nutzer_client: Client, make_risk: MakeRisk) -> None:
    risk = make_risk(RiskStatus.CATEGORIZED)
    assert nutzer_client.get(f"/risiken/{risk.pk}/bewertung/").status_code == 403


@pytest.mark.req("M-05")
def test_m_05_status_change_checks_role(
    client: Client, make_risk: MakeRisk, users: dict[str, User]
) -> None:
    risk = make_risk(RiskStatus.VALIDATED)
    client.force_login(users["ciso"])
    assert client.post(f"/risiken/{risk.pk}/status/", {"target": "CLOSED"}).status_code == 403

    client.force_login(users["rm"])
    response = client.post(f"/risiken/{risk.pk}/status/", {"target": "CLOSED"})
    assert response.status_code == 302
    risk.refresh_from_db()
    assert risk.status == RiskStatus.CLOSED


@pytest.mark.req("M-04")
def test_m_04_approval_page_lists_only_requests_of_others(
    client: Client, users: dict[str, User], make_risk: MakeRisk
) -> None:
    from apps.risks.services import reclassify

    risk = make_risk(RiskStatus.SCORED)
    reclassify(
        risk,
        users["rm"],
        confidentiality=False,
        integrity=False,
        availability=True,
        origin=Origin.TECHNICAL_FAILURE,
        assets=[],
    )
    request = risk.approval_requests.get()

    client.force_login(users["rm"])
    assert f"/freigaben/{request.pk}/" not in client.get("/freigaben/").content.decode()
    client.force_login(users["rm2"])
    assert f"/freigaben/{request.pk}/" in client.get("/freigaben/").content.decode()
    response = client.post(f"/freigaben/{request.pk}/", {"decision": "approve"})
    assert response.status_code == 302
    request.refresh_from_db()
    assert request.state == ApprovalState.APPROVED


@pytest.mark.req("AK-01.1")
def test_ak_01_1_preview_container_keeps_its_own_trigger(nutzer_client: Client) -> None:
    """The swapped element must carry the htmx trigger itself; a trigger bound to the old
    elements ("change from:#id_…") stops working after the first swap."""
    form_page = nutzer_client.get("/risiken/neu/").content.decode()
    preview = nutzer_client.post(
        "/risiken/kategorie-vorschau/", {"integrity": "on"}, headers={"HX-Request": "true"}
    ).content.decode()
    for html in (form_page, preview):
        container = re.search(r'<div id="classification"[^>]*>', html)
        assert container
        assert 'hx-trigger="change"' in container.group(0)
        assert 'hx-swap="outerHTML"' in container.group(0)
    assert "change from:" not in form_page


@pytest.mark.req("AK-02.3")
def test_ak_02_3_live_preview_is_not_triggered_by_the_form(
    rm_client: Client, make_risk: MakeRisk
) -> None:
    """htmx validates a triggering <form> before the request and would drop the preview for an
    out-of-range value; the trigger therefore sits on a container inside the form."""
    risk = make_risk(RiskStatus.CATEGORIZED)
    html = rm_client.get(f"/risiken/{risk.pk}/bewertung/").content.decode()
    form_tag = re.search(r'<form method="post"[^>]*>', html)
    assert form_tag
    assert "hx-post" not in form_tag.group(0)
    assert re.search(
        r'<div[^>]*hx-post="/risiken/score-vorschau/"[^>]*hx-include="closest form"', html
    )
