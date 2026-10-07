"""M-06: the audit log only grows."""

import pytest
from django.db import IntegrityError, connection, transaction

from apps.audit.models import AppendOnlyError, AuditAction, AuditEntry
from apps.audit.services import record
from apps.risks.models import RiskStatus
from tests.conftest import MakeRisk

pytestmark = [pytest.mark.req("M-06"), pytest.mark.django_db]


@pytest.fixture
def entry(make_risk: MakeRisk, users) -> AuditEntry:
    risk = make_risk(RiskStatus.SCORED)
    return record(
        actor=users["rm"],
        action=AuditAction.FIELD_CHANGED,
        obj=risk.assessment,
        risk=risk,
        field="probability",
        old=4,
        new=3,
    )


def test_m_06_entry_records_author_time_old_and_new_value(entry: AuditEntry, users) -> None:
    entry.refresh_from_db()
    assert entry.actor == users["rm"]
    assert entry.created_at is not None
    assert (entry.field, entry.old_value, entry.new_value) == ("probability", "4", "3")


def test_m_06_saved_entry_cannot_be_changed_via_orm(entry: AuditEntry) -> None:
    entry.new_value = "5"
    with pytest.raises(AppendOnlyError):
        entry.save()


def test_m_06_bulk_update_is_refused_by_the_database(entry: AuditEntry) -> None:
    with pytest.raises(IntegrityError), transaction.atomic():
        AuditEntry.objects.filter(pk=entry.pk).update(new_value="5")


def test_m_06_raw_update_is_refused_by_the_database(entry: AuditEntry) -> None:
    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("UPDATE audit_auditentry SET old_value = '1' WHERE id = %s", [entry.pk])
