"""Demo data for development (``manage.py seed_demo``): a register that covers every state,
built through the services, plus the lookup of the demo accounts. No Keycloak needed."""

from collections import Counter
from pathlib import Path
from typing import Any

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.keycloak import AccountError, sync_users
from apps.accounts.models import Role, User
from apps.audit.models import AuditAction, AuditEntry
from apps.notifications.models import NotificationKind, NotificationStatus
from apps.notifications.services import unresolved_failures
from apps.risks.demo import seed
from apps.risks.models import ApprovalKind, ApprovalRequest, ApprovalState, Risk, RiskCategory
from apps.risks.services import visible_risks

ROOT = Path(__file__).resolve().parent.parent
ASSETS_CSV = ROOT / "src" / "apps" / "cmdb" / "data" / "assets.csv"


@pytest.fixture
def demo_users(users: dict[str, User]) -> dict[str, User]:
    call_command("import_assets", str(ASSETS_CSV), verbosity=0)
    return {
        "melder": users["nutzer"],
        "rm.mueller": users["rm"],
        "rm.schmidt": users["rm2"],
        "ciso": users["ciso"],
    }


def test_demo_data_covers_every_state_and_both_categories(demo_users: dict[str, User]) -> None:
    assert seed(demo_users) == 13

    assert Counter(Risk.objects.values_list("status", flat=True)) == {
        "DRAFT": 2,
        "CATEGORIZED": 2,
        "SCORED": 2,
        "ESCALATED": 3,
        "VALIDATED": 2,
        "CLOSED": 1,
        "OBSOLETE": 1,
    }
    categories = set(Risk.objects.values_list("assessment__category", flat=True))
    assert {RiskCategory.IS_RISIKO, RiskCategory.IT_RISIKO} <= categories
    obsolete = Risk.objects.get(status="OBSOLETE")
    assert Risk.objects.get(predecessor=obsolete).status == "DRAFT"


def test_demo_data_has_open_and_decided_approvals(demo_users: dict[str, User]) -> None:
    seed(demo_users)

    pending = ApprovalRequest.objects.filter(state=ApprovalState.PENDING)
    assert sorted(pending.values_list("kind", flat=True)) == sorted(
        [ApprovalKind.CATEGORY_TO_IT, ApprovalKind.SCORE_DOWNGRADE]
    )
    approved = ApprovalRequest.objects.get(state=ApprovalState.APPROVED)
    assert approved.requested_by != approved.decided_by  # four eyes (M-04)


def test_demo_data_has_one_failed_and_otherwise_queued_notifications(
    demo_users: dict[str, User],
) -> None:
    seed(demo_users)

    flagged = {n.risk.title for n in unresolved_failures()}
    assert flagged == {"Ungepatchte VPN-Appliance"}
    assert AuditEntry.objects.filter(action=AuditAction.NOTIFICATION_FAILED).exists()
    # The rest is left to the worker, so the e-mails reach Mailpit
    queued = Risk.objects.filter(notifications__status=NotificationStatus.PENDING).distinct()
    assert queued.count() == 4
    assert queued.filter(notifications__kind=NotificationKind.IT_OPS_HANDOVER).exists()


def test_demo_data_is_written_through_the_services(demo_users: dict[str, User]) -> None:
    seed(demo_users)

    for risk in Risk.objects.all():
        assert AuditEntry.objects.filter(risk=risk, action=AuditAction.CREATED).exists()
    assert AuditEntry.objects.filter(action=AuditAction.STATUS_CHANGED).count() >= 20


def test_demo_data_shows_the_reporter_only_own_risks(demo_users: dict[str, User]) -> None:
    seed(demo_users)

    melder = demo_users["melder"]
    assert visible_risks(melder).count() == 4
    assert set(visible_risks(melder).values_list("reporter", flat=True)) == {melder.pk}
    assert visible_risks(demo_users["rm.mueller"]).count() == 13


def test_demo_data_leaves_a_register_that_is_not_empty_alone(demo_users: dict[str, User]) -> None:
    seed(demo_users)

    assert seed(demo_users) == 0
    assert Risk.objects.count() == 13


def test_demo_data_command_refuses_without_debug(db: None, settings: Any) -> None:
    settings.DEBUG = False

    with pytest.raises(CommandError, match="DJANGO_DEBUG"):
        call_command("seed_demo")


def _claims(username: str, sub: str, *groups: str) -> dict[str, Any]:
    return {"sub": sub, "preferred_username": username, "groups": list(groups)}


def test_demo_accounts_are_created_like_a_login(db: None) -> None:
    users = sync_users([_claims("rm.mueller", "kc-1", "/RISK_MANAGER")])

    user = User.objects.get(oidc_subject="kc-1")
    assert users == {"rm.mueller": user}
    assert (user.username, user.role, user.has_usable_password()) == (
        "rm.mueller",
        Role.RISK_MANAGER,
        False,
    )


def test_demo_accounts_reuse_a_user_who_logged_in_before(make_user: Any) -> None:
    existing = make_user(Role.NUTZER, "melder")  # oidc_subject == username in the fixture

    users = sync_users([_claims("melder", "melder", "/NUTZER")])

    assert users["melder"].pk == existing.pk
    assert User.objects.filter(username="melder").count() == 1


def test_demo_accounts_reject_a_conflicting_or_roleless_account(make_user: Any) -> None:
    make_user(Role.NUTZER, "melder")

    with pytest.raises(AccountError, match="another Keycloak ID"):
        sync_users([_claims("melder", "other-sub", "/NUTZER")])
    with pytest.raises(AccountError, match="no unique role group"):
        sync_users([_claims("ohne-rolle", "kc-9")])
