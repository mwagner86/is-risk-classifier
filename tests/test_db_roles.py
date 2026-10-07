"""The application connects with a role that cannot delete or truncate domain data and cannot
change the audit log, independent of the triggers (INV-03, M-06)."""

import pytest
from django.core.management import call_command
from django.db import connection

pytestmark = pytest.mark.django_db

ROLE = "isrisk_app_test"
DOMAIN_TABLES = [
    "risks_risk",
    "risks_riskassessment",
    "risks_ciatriad",
    "risks_approvalrequest",
    "notifications_notification",
    "cmdb_asset",
    "accounts_user",
    "exports_export",
]


@pytest.fixture
def app_role(settings) -> str:
    settings.DB_APP_ROLE = ROLE
    settings.DB_APP_PASSWORD = "test-only-password"
    call_command("setup_db_roles")
    return ROLE


def _can(role: str, table: str, privilege: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT has_table_privilege(%s, %s, %s)", [role, table, privilege])
        return bool(cursor.fetchone()[0])


@pytest.mark.req("INV-03")
@pytest.mark.parametrize("table", DOMAIN_TABLES)
def test_inv_03_app_role_cannot_delete_or_truncate(app_role: str, table: str) -> None:
    assert _can(app_role, table, "SELECT")
    assert _can(app_role, table, "INSERT")
    assert not _can(app_role, table, "DELETE")
    assert not _can(app_role, table, "TRUNCATE")
    assert not _can(app_role, table, "TRIGGER")


@pytest.mark.req("M-06")
def test_m_06_app_role_can_only_append_to_the_audit_log(app_role: str) -> None:
    assert _can(app_role, "audit_auditentry", "INSERT")
    assert _can(app_role, "audit_auditentry", "SELECT")
    assert not _can(app_role, "audit_auditentry", "UPDATE")
    assert not _can(app_role, "audit_auditentry", "DELETE")


def test_app_role_may_delete_only_where_the_application_must(app_role: str) -> None:
    # Logout removes the session; unlinking an asset removes a row of the m:n table
    assert _can(app_role, "django_session", "DELETE")
    assert _can(app_role, "risks_riskassessment_assets", "DELETE")


def test_app_role_is_not_privileged(app_role: str) -> None:
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT rolsuper, rolcreatedb, rolcreaterole, rolbypassrls "
            "FROM pg_roles WHERE rolname = %s",
            [app_role],
        )
        assert cursor.fetchone() == (False, False, False, False)


def test_setup_db_roles_is_idempotent(app_role: str) -> None:
    call_command("setup_db_roles")
    assert not _can(app_role, "risks_risk", "DELETE")
