"""Notifications for a risk. The table doubles as outbox: rows are written in the same
transaction as the escalation and sent afterwards by the worker (asynchronous, AK-03.1)."""

from django.db import models

from apps.core.models import BaseModel


class NotificationKind(models.TextChoices):
    ESCALATION = "ESCALATION", "Eskalation"
    IT_OPS_HANDOVER = "IT_OPS_HANDOVER", "Weitergabe an IT-Operations"


class Channel(models.TextChoices):
    EMAIL = "EMAIL", "E-Mail"
    SMS = "SMS", "SMS"


class NotificationStatus(models.TextChoices):
    PENDING = "PENDING", "Ausstehend"
    DELIVERED = "DELIVERED", "Zugestellt"
    FAILED = "FAILED", "Fehlgeschlagen"


class Notification(BaseModel):
    risk = models.ForeignKey("risks.Risk", on_delete=models.PROTECT, related_name="notifications")
    kind = models.CharField(max_length=32, choices=NotificationKind.choices)
    channel = models.CharField(max_length=8, choices=Channel.choices)
    recipient = models.CharField(max_length=254)
    # M-09: identifier and link only, never title, description or assets
    subject = models.CharField(max_length=200)
    body = models.TextField()
    status = models.CharField(
        max_length=16, choices=NotificationStatus.choices, default=NotificationStatus.PENDING
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    dispatched_at = models.DateTimeField("Versendet am", null=True, blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = "Notifikation"
        verbose_name_plural = "Notifikationen"
        indexes = [models.Index(fields=["status", "created_at"], name="notification_outbox_idx")]

    @property
    def is_delivered(self) -> bool:
        return self.status == NotificationStatus.DELIVERED
