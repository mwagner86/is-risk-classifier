"""Notifications sent for a risk (escalation, hand-over to IT operations).

Iteration 1 holds only the attributes of the class model; the outbox fields follow with the
escalation in iteration 2.
"""

from django.db import models

from apps.core.models import BaseModel


class Notification(BaseModel):
    risk = models.ForeignKey("risks.Risk", on_delete=models.PROTECT, related_name="notifications")
    dispatched_at = models.DateTimeField("Versendet am", null=True, blank=True)
    is_delivered = models.BooleanField("Zugestellt", default=False)

    class Meta(BaseModel.Meta):
        verbose_name = "Notifikation"
        verbose_name_plural = "Notifikationen"
