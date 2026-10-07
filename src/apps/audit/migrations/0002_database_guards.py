"""Database-level guards: no physical deletion (INV-03) and an append-only audit log (M-06)."""

from django.db import migrations

from apps.core.db import append_only


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_trigger_functions"),
        ("audit", "0001_initial"),
    ]
    operations = [
        append_only("audit_auditentry"),
    ]
