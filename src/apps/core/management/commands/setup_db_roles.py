"""Create or update the database role the application runs with.

Migrations run as the owner of the database. The application gets a separate role that may read,
insert and update, but not delete or truncate domain data, not alter the audit log and not change
the schema — so INV-03 and the append-only audit log (M-06) hold even if the application is
compromised, and the role cannot drop the guarding triggers either. Idempotent; run after migrate.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from psycopg import sql

# The only deletes the application performs: logout removes the session, unlinking an asset
# removes a row of the m:n table
DELETE_ALLOWED = ("django_session", "risks_riskassessment_assets")
APPEND_ONLY = ("audit_auditentry",)


class Command(BaseCommand):
    help = "Create or update the restricted database role of the application."

    def handle(self, *args: Any, **options: Any) -> None:
        role, password = settings.DB_APP_ROLE, settings.DB_APP_PASSWORD
        if not password:
            raise CommandError("POSTGRES_APP_PASSWORD is not set")
        if role == connection.settings_dict["USER"]:
            raise CommandError("the application role must not be the database owner")

        name = sql.Identifier(role)
        connection.ensure_connection()
        raw = connection.connection
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", [role])
            verb = "ALTER" if cursor.fetchone() else "CREATE"
            statements = [
                sql.SQL(
                    verb + " ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOBYPASSRLS NOREPLICATION PASSWORD {}"
                ).format(name, sql.Literal(password)),
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(connection.settings_dict["NAME"]), name
                ),
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(name),
                sql.SQL("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM {}").format(name),
                sql.SQL("GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO {}").format(
                    name
                ),
                sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(name),
                *[
                    sql.SQL("REVOKE UPDATE ON {} FROM {}").format(sql.Identifier(t), name)
                    for t in APPEND_ONLY
                ],
                *[
                    sql.SQL("GRANT DELETE ON {} TO {}").format(sql.Identifier(t), name)
                    for t in DELETE_ALLOWED
                ],
            ]
            for statement in statements:
                cursor.execute(statement.as_string(raw))
        action = "created" if verb == "CREATE" else "updated"
        self.stdout.write(f"database role {role} {action} with restricted privileges")
