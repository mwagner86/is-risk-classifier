"""PostgreSQL triggers that enforce INV-03 and the append-only audit log (M-06) in the database.

The ORM guards in ``apps.core.models`` stop accidental deletes in application code; these triggers
also stop raw SQL, a misbehaving migration or a bulk operation that bypasses model methods.
"""

from django.db import migrations

CREATE_FUNCTIONS = """
CREATE OR REPLACE FUNCTION forbid_delete() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'INV-03: physical deletion from % is forbidden', TG_TABLE_NAME
        USING ERRCODE = 'restrict_violation';
END
$$;

CREATE OR REPLACE FUNCTION forbid_modification() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'M-06: % is append-only, % is forbidden', TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'restrict_violation';
END
$$;
"""

DROP_FUNCTIONS = """
DROP FUNCTION IF EXISTS forbid_modification();
DROP FUNCTION IF EXISTS forbid_delete();
"""


def forbid_delete(table: str) -> migrations.RunSQL:
    """Block DELETE and TRUNCATE on ``table``."""
    return migrations.RunSQL(
        sql=f"""
        CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_delete();
        CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION forbid_delete();
        """,
        reverse_sql=f"""
        DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};
        DROP TRIGGER IF EXISTS {table}_no_delete ON {table};
        """,
    )


def append_only(table: str) -> migrations.RunSQL:
    """Block UPDATE, DELETE and TRUNCATE on ``table``: rows can only be inserted."""
    return migrations.RunSQL(
        sql=f"""
        CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION forbid_modification();
        CREATE TRIGGER {table}_no_truncate BEFORE TRUNCATE ON {table}
            FOR EACH STATEMENT EXECUTE FUNCTION forbid_modification();
        """,
        reverse_sql=f"""
        DROP TRIGGER IF EXISTS {table}_no_truncate ON {table};
        DROP TRIGGER IF EXISTS {table}_append_only ON {table};
        """,
    )
