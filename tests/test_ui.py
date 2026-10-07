"""Navigation, read-only pages, filters and the design rules (WCAG AA, reduced motion, no
third-party requests)."""

import re
from pathlib import Path

import pytest
from django.test import Client

from apps.accounts.models import Role, User
from apps.cmdb.models import Asset
from apps.risks.models import RiskCategory, RiskStatus
from tests.conftest import MakeRisk

CSS = Path(__file__).resolve().parent.parent / "src" / "static" / "css" / "app.css"
TEMPLATES = Path(__file__).resolve().parent.parent / "src" / "templates"

# (foreground token, background token, minimum ratio). 4.5 for text, 3 for large text and UI.
CONTRAST_PAIRS = [
    *[("text", bg, 4.5) for bg in ("bg", "bg-2", "surface-1", "surface-2", "surface-3")],
    *[("muted", bg, 4.5) for bg in ("bg", "bg-2", "surface-1", "surface-2")],
    *[("on-level", f"level-{lvl}", 4.5) for lvl in ("critical", "high", "medium", "low")],
    *[("accent", bg, 4.5) for bg in ("bg", "surface-1", "surface-2", "surface-3")],
    ("on-primary", "primary", 4.5),
    ("danger-strong", "danger-tint", 4.5),
    ("text", "danger-tint", 4.5),
    *[("critical", bg, 4.5) for bg in ("bg", "surface-1", "surface-2")],
    *[("faint", bg, 3.0) for bg in ("bg", "surface-1")],  # decoration and large text only
]


def _tokens() -> dict[str, str]:
    return dict(re.findall(r"--color-([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})\s*;", CSS.read_text()))


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]


def _contrast(a: str, b: str) -> float:
    high, low = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (high + 0.05) / (low + 0.05)


@pytest.mark.parametrize(("fg", "bg", "minimum"), CONTRAST_PAIRS)
def test_wcag_aa_contrast_of_design_tokens(fg: str, bg: str, minimum: float) -> None:
    tokens = _tokens()
    assert _contrast(tokens[fg], tokens[bg]) >= minimum


def _blocks(css: str, prelude: str) -> list[str]:
    """Bodies of the at-rule blocks whose prelude contains ``prelude``."""
    bodies = []
    for match in re.finditer(re.escape(prelude), css):
        start = css.index("{", match.end())
        depth, pos = 1, start + 1
        while depth:
            depth += {"{": 1, "}": -1}.get(css[pos], 0)
            pos += 1
        bodies.append(css[start + 1 : pos - 1])
    return bodies


@pytest.mark.req("AK-03.3")
def test_decision_7_animation_only_without_reduced_motion() -> None:
    css = re.sub(r"/\*.*?\*/", "", CSS.read_text(), flags=re.S)
    allowed = "".join(_blocks(css, "@media (prefers-reduced-motion: no-preference)"))
    animations = re.findall(r"animation\s*:[^;]+;", css)
    assert animations, "the flag should pulse briefly where motion is welcome"
    for declaration in animations:
        assert declaration in allowed
        # Finite and at most 5 s in total (WCAG 2.2.2), at most 3 flashes per second (2.3.1)
        duration_match = re.search(r"([\d.]+)s", declaration)
        assert duration_match
        duration = float(duration_match.group(1))
        count = re.search(r"\s(\d+)\s*;", declaration)
        assert count, "iteration count must be finite"
        assert duration * int(count.group(1)) <= 5
        assert duration >= 1 / 3
    for template in TEMPLATES.rglob("*.html"):
        assert "animate-" not in template.read_text(), template


@pytest.mark.django_db
def test_no_third_party_requests(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["rm"])
    html = client.get("/").content.decode()
    sources = re.findall(r'<(?:script|link|img)[^>]+(?:src|href)="([^"]+)"', html)
    assert sources
    assert all(src.startswith("/static/") for src in sources), sources
    assert not re.search(r"url\(\s*['\"]?https?:", CSS.read_text())
    assert "@import url" not in CSS.read_text()


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("role", "visible", "hidden"),
    [
        (Role.NUTZER, {"Dashboard", "Risiken", "Assets"}, {"Eskalationen", "Freigaben"}),
        (Role.RISK_MANAGER, {"Risiken", "Eskalationen", "Freigaben"}, set()),
        (Role.CISO, {"Risiken", "Eskalationen"}, {"Freigaben"}),
        (Role.ADMIN, {"Dashboard", "Eskalationen"}, {"Freigaben"}),
    ],
)
def test_navigation_matches_role(
    role: Role, visible: set[str], hidden: set[str], client: Client, make_user
) -> None:
    client.force_login(make_user(role))
    nav = re.search(
        r"<nav[^>]*aria-label=\"Hauptnavigation\".*?</nav>", client.get("/").content.decode(), re.S
    )
    assert nav
    for label in visible:
        assert label in nav.group(0)
    for label in hidden:
        assert label not in nav.group(0)


@pytest.mark.django_db
@pytest.mark.req("M-05")
def test_m_05_escalation_page_is_not_for_reporters(client: Client, users: dict[str, User]) -> None:
    client.force_login(users["nutzer"])
    assert client.get("/eskalationen/").status_code == 403


@pytest.mark.django_db
@pytest.mark.parametrize("role", list(Role))
def test_assets_are_read_only_for_everyone(
    role: Role, client: Client, make_user, asset: Asset
) -> None:
    client.force_login(make_user(role))
    page = client.get("/assets/")
    assert page.status_code == 200
    assert asset.name in page.content.decode()
    assert "<form" not in re.sub(r"<header.*?</header>", "", page.content.decode(), flags=re.S)
    assert client.post("/assets/").status_code == 405


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("category=IT_RISIKO", {"it"}),
        ("level=critical", {"crit"}),
        ("p=1&i=2", {"low"}),
        ("status=VALIDATED", {"low"}),
        ("", {"crit", "it", "low"}),
    ],
)
def test_risk_list_filters(
    query: str, expected: set[str], client: Client, users: dict[str, User], make_risk: MakeRisk
) -> None:
    risks = {
        "crit": make_risk(RiskStatus.ESCALATED, probability=5, impact=4),
        "it": make_risk(
            RiskStatus.SCORED, category=RiskCategory.IT_RISIKO, probability=2, impact=3
        ),
        "low": make_risk(RiskStatus.VALIDATED, probability=1, impact=2),
    }
    client.force_login(users["rm"])
    html = client.get(f"/risiken/?{query}").content.decode()
    shown = {key for key, risk in risks.items() if f"/risiken/{risk.pk}/" in html}
    assert shown == expected
