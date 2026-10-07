from django.db import migrations, models


class Migration(migrations.Migration):
    """Turn the notification of the class model into an outbox row (iteration 2).

    No notifications existed before, so the placeholder defaults never reach a row.
    """

    dependencies = [("notifications", "0002_database_guards")]

    operations = [
        migrations.RemoveField(model_name="notification", name="is_delivered"),
        migrations.AddField(
            model_name="notification",
            name="kind",
            field=models.CharField(
                choices=[("ESCALATION", "Eskalation"), ("IT_OPS_HANDOVER", "Weitergabe an IT-Operations")],
                default="ESCALATION",
                max_length=32,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="notification",
            name="channel",
            field=models.CharField(
                choices=[("EMAIL", "E-Mail"), ("SMS", "SMS")], default="EMAIL", max_length=8
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="notification",
            name="recipient",
            field=models.CharField(default="", max_length=254),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="notification",
            name="subject",
            field=models.CharField(default="", max_length=200),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="notification",
            name="body",
            field=models.TextField(default=""),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="notification",
            name="status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Ausstehend"),
                    ("DELIVERED", "Zugestellt"),
                    ("FAILED", "Fehlgeschlagen"),
                ],
                default="PENDING",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="notification",
            name="attempts",
            field=models.PositiveSmallIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="notification",
            name="last_error",
            field=models.TextField(blank=True),
        ),
        migrations.AddIndex(
            model_name="notification",
            index=models.Index(fields=["status", "created_at"], name="notification_outbox_idx"),
        ),
    ]
