"""Database-level guards: no physical deletion (INV-03)."""

from django.db import migrations

from apps.core.db import forbid_delete


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0001_trigger_functions"),
        ("notifications", "0001_initial"),
    ]
    operations = [
        forbid_delete("notifications_notification"),
    ]
