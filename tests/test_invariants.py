"""INV-02 (category is exactly IS or IT) and INV-03 (nothing is ever deleted physically)."""

import pytest
from django.db import DataError, IntegrityError, connection, transaction
from django.db.models import Model

from apps.accounts.models import User
from apps.audit.models import AuditAction, AuditEntry
from apps.cmdb.models import Asset
from apps.core.models import DeletionForbiddenError
from apps.exports.models import Export
from apps.notifications.models import Notification
from apps.risks.models import (
    ApprovalKind,
    ApprovalRequest,
    CIATriad,
    Risk,
    RiskAssessment,
    RiskCategory,
    RiskStatus,
)
from tests.conftest import MakeRisk

pytestmark = pytest.mark.django_db

PROTECTED_MODELS: list[type[Model]] = [
    Risk,
    RiskAssessment,
    CIATriad,
    ApprovalRequest,
    Notification,
    Asset,
    User,
    AuditEntry,
    Export,
]


@pytest.fixture
def one_of_each(make_risk: MakeRisk, users: dict[str, User]) -> dict[type[Model], Model]:
    risk = make_risk(RiskStatus.SCORED)
    approval = ApprovalRequest.objects.create(
        risk=risk,
        kind=ApprovalKind.SCORE_DOWNGRADE,
        proposed_probability=1,
        proposed_impact=1,
        requested_by=users["rm"],
    )
    notification = Notification.objects.create(risk=risk)
    export = Export.objects.create(
        exported_by=users["rm"], format="csv", filter_description="x", query="x", row_count=0
    )
    entry = AuditEntry.objects.create(
        action=AuditAction.CREATED, risk=risk, object_type="Risk", object_id=risk.pk
    )
    return {
        Risk: risk,
        RiskAssessment: risk.assessment,
        CIATriad: risk.assessment.cia,
        ApprovalRequest: approval,
        Notification: notification,
        Asset: risk.assessment.assets.get(),
        User: users["nutzer"],
        AuditEntry: entry,
        Export: export,
    }


# --- INV-02 ---------------------------------------------------------------------------------


@pytest.mark.req("INV-02")
def test_inv_02_exactly_two_categories() -> None:
    assert RiskCategory.values == ["IS_RISIKO", "IT_RISIKO"]


@pytest.mark.req("INV-02")
@pytest.mark.parametrize("value", ["BEIDES", "IS_RISIKO,IT_RISIKO", "SONSTIGES", ""])
def test_inv_02_database_rejects_any_other_category(value: str, make_risk: MakeRisk) -> None:
    assessment = make_risk(RiskStatus.CATEGORIZED).assessment
    # Too long for the column is a DataError, anything else violates the check constraint
    with pytest.raises((IntegrityError, DataError)), transaction.atomic():
        RiskAssessment.objects.filter(pk=assessment.pk).update(category=value)


@pytest.mark.req("INV-02")
def test_inv_02_reclassification_at_runtime(make_risk: MakeRisk) -> None:
    assessment = make_risk(RiskStatus.CATEGORIZED).assessment
    assessment.category = RiskCategory.IT_RISIKO
    assessment.save()
    assessment.refresh_from_db()
    assert assessment.category == RiskCategory.IT_RISIKO


# --- INV-03 ---------------------------------------------------------------------------------


@pytest.mark.req("INV-03")
@pytest.mark.parametrize("model", PROTECTED_MODELS, ids=lambda m: m.__name__)
def test_inv_03_instance_delete_is_refused(
    model: type[Model], one_of_each: dict[type[Model], Model]
) -> None:
    with pytest.raises(DeletionForbiddenError):
        one_of_each[model].delete()
    assert model._default_manager.filter(pk=one_of_each[model].pk).exists()


@pytest.mark.req("INV-03")
@pytest.mark.parametrize("model", PROTECTED_MODELS, ids=lambda m: m.__name__)
def test_inv_03_bulk_delete_is_refused(
    model: type[Model], one_of_each: dict[type[Model], Model]
) -> None:
    with pytest.raises(DeletionForbiddenError):
        model._default_manager.all().delete()


@pytest.mark.req("INV-03")
@pytest.mark.parametrize("model", PROTECTED_MODELS, ids=lambda m: m.__name__)
def test_inv_03_database_refuses_raw_delete(
    model: type[Model], one_of_each: dict[type[Model], Model]
) -> None:
    table = model._meta.db_table
    with (
        pytest.raises(IntegrityError, match=r"INV-03|M-06"),
        transaction.atomic(),
        connection.cursor() as cursor,
    ):
        cursor.execute(f"DELETE FROM {table} WHERE id = %s", [one_of_each[model].pk])  # noqa: S608


@pytest.mark.req("INV-03")
@pytest.mark.parametrize("model", PROTECTED_MODELS, ids=lambda m: m.__name__)
def test_inv_03_database_refuses_truncate(
    model: type[Model], one_of_each: dict[type[Model], Model]
) -> None:
    table = model._meta.db_table
    with transaction.atomic(), connection.cursor() as cursor:
        # Django's foreign keys are DEFERRABLE; fire their pending checks first, otherwise
        # PostgreSQL refuses the TRUNCATE for that reason before our trigger is reached
        cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        with pytest.raises(IntegrityError, match=r"INV-03|M-06"), transaction.atomic():
            cursor.execute(f"TRUNCATE {table} CASCADE")


# --- score is derived, never set ------------------------------------------------------------


def test_score_is_always_the_product(make_risk: MakeRisk) -> None:
    assessment = make_risk(RiskStatus.SCORED, probability=4, impact=5).assessment
    assert assessment.score == 20
    with pytest.raises(IntegrityError), transaction.atomic():
        RiskAssessment.objects.filter(pk=assessment.pk).update(score=3)


@pytest.mark.parametrize(
    ("field", "value"), [("probability", 0), ("probability", 6), ("impact", 9)]
)
def test_database_rejects_values_outside_1_to_5(
    field: str, value: int, make_risk: MakeRisk
) -> None:
    assessment = make_risk(RiskStatus.SCORED).assessment
    with pytest.raises(IntegrityError), transaction.atomic():
        RiskAssessment.objects.filter(pk=assessment.pk).update(**{field: value})
