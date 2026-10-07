"""US-01: the system categorises a new risk from protection goals and origin."""

from itertools import product
from typing import Any

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.cmdb.models import Asset
from apps.notifications.gateway import OutgoingMessage
from apps.risks.classification import categorize
from apps.risks.models import ApprovalKind, ApprovalState, Origin, Risk, RiskCategory, RiskStatus
from apps.risks.services import capture

ORIGIN_MISSING = "Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden"

# (confidentiality, integrity, availability) with C or I set
C_OR_I = [flags for flags in product([False, True], repeat=3) if flags[0] or flags[1]]
OTHER_ORIGINS = [o for o in Origin if o != Origin.TECHNICAL_FAILURE]


def _data(asset: Asset | None = None, **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "title": "Ransomware auf dem Dateiserver",
        "description": "Verschlüsselte Freigaben im Fachbereich",
        "confidentiality": True,
        "integrity": False,
        "availability": False,
        "origin": Origin.DELIBERATE_ATTACK,
        "assets": [asset] if asset else [],
    }
    data.update(overrides)
    return data


# --- AK-01.1 --------------------------------------------------------------------------------


@pytest.mark.req("AK-01.1")
@pytest.mark.parametrize("flags", C_OR_I)
@pytest.mark.parametrize("origin", list(Origin))
def test_ak_01_1_confidentiality_or_integrity_is_always_is_risk(
    flags: tuple[bool, bool, bool], origin: Origin
) -> None:
    assert categorize(*flags, origin) == RiskCategory.IS_RISIKO


@pytest.mark.req("AK-01.1")
@pytest.mark.django_db
def test_ak_01_1_is_risk_requires_assets(users: dict[str, User], asset: Asset) -> None:
    with pytest.raises(ValidationError) as excinfo:
        capture(users["nutzer"], **_data())
    assert "assets" in excinfo.value.message_dict
    assert not Risk.objects.exists()

    risk = capture(users["nutzer"], **_data(asset))
    assert risk.status == RiskStatus.CATEGORIZED
    assert risk.assessment.category == RiskCategory.IS_RISIKO
    assert list(risk.assessment.assets.all()) == [asset]


# --- AK-01.2 --------------------------------------------------------------------------------


@pytest.mark.req("AK-01.2")
def test_ak_01_2_availability_and_technical_failure_is_it_risk() -> None:
    assert categorize(False, False, True, Origin.TECHNICAL_FAILURE) == RiskCategory.IT_RISIKO


@pytest.mark.req("AK-01.2")
@pytest.mark.django_db
def test_ak_01_2_it_risk_is_handed_over_to_it_operations_after_approval(
    users: dict[str, User], sent_messages: list[OutgoingMessage]
) -> None:
    from apps.notifications.models import Notification, NotificationKind
    from apps.notifications.services import process_outbox
    from apps.risks.services import decide

    risk = capture(
        users["nutzer"],
        **_data(confidentiality=False, availability=True, origin=Origin.TECHNICAL_FAILURE),
    )
    # M-04: not handed over before a risk manager approved the IT categorisation
    assert not Notification.objects.filter(kind=NotificationKind.IT_OPS_HANDOVER).exists()

    decide(risk.approval_requests.get(), users["rm"], approve=True)
    process_outbox()

    risk.assessment.refresh_from_db()
    assert risk.assessment.category == RiskCategory.IT_RISIKO
    handover = Notification.objects.get(risk=risk, kind=NotificationKind.IT_OPS_HANDOVER)
    assert handover.is_delivered
    assert [m.recipient for m in sent_messages] == ["it-ops@example.org"]


@pytest.mark.req("US-01")
@pytest.mark.parametrize("origin", OTHER_ORIGINS)
def test_us_01_only_availability_with_other_origin_is_is_risk(origin: Origin) -> None:
    assert categorize(False, False, True, origin) == RiskCategory.IS_RISIKO


# --- AK-01.3 and the other blocking cases ---------------------------------------------------


@pytest.mark.req("AK-01.3")
@pytest.mark.django_db
def test_ak_01_3_missing_origin_blocks_saving(users: dict[str, User], asset: Asset) -> None:
    with pytest.raises(ValidationError) as excinfo:
        capture(users["nutzer"], **_data(asset, origin=""))
    assert excinfo.value.message_dict["origin"] == [ORIGIN_MISSING]
    assert not Risk.objects.exists()


@pytest.mark.req("US-01")
@pytest.mark.django_db
def test_us_01_no_protection_goal_blocks_saving(users: dict[str, User], asset: Asset) -> None:
    with pytest.raises(ValidationError) as excinfo:
        capture(users["nutzer"], **_data(asset, confidentiality=False))
    assert "cia" in excinfo.value.message_dict
    assert not Risk.objects.exists()


@pytest.mark.req("US-01")
def test_us_01_category_needs_goal_and_origin() -> None:
    assert categorize(False, False, False, Origin.DELIBERATE_ATTACK) is None
    assert categorize(True, False, False, "") is None


# --- M-04 at capture ------------------------------------------------------------------------


@pytest.mark.req("M-04")
@pytest.mark.django_db
def test_m_04_it_categorisation_at_capture_is_only_a_request(users: dict[str, User]) -> None:
    risk = capture(
        users["nutzer"],
        **_data(confidentiality=False, availability=True, origin=Origin.TECHNICAL_FAILURE),
    )

    assert risk.assessment.category == RiskCategory.IS_RISIKO  # the stricter one applies
    request = risk.approval_requests.get()
    assert request.kind == ApprovalKind.CATEGORY_TO_IT
    assert request.state == ApprovalState.PENDING
    assert request.requested_by == users["nutzer"]
