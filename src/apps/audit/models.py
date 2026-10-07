"""Append-only audit log (M-06, M-07): who changed what, when, from which value to which."""

from typing import Any

from django.db import models

from apps.core.models import BaseModel


class AuditAction(models.TextChoices):
    CREATED = "CREATED", "Angelegt"
    FIELD_CHANGED = "FIELD_CHANGED", "Wert geändert"
    STATUS_CHANGED = "STATUS_CHANGED", "Status geändert"
    APPROVAL_REQUESTED = "APPROVAL_REQUESTED", "Freigabe beantragt"
    APPROVAL_DECIDED = "APPROVAL_DECIDED", "Freigabe entschieden"
    NOTIFICATION_FAILED = "NOTIFICATION_FAILED", "Notifikation fehlgeschlagen"
    NOTIFICATION_RESENT = "NOTIFICATION_RESENT", "Notifikation erneut gesendet"
    EXPORTED = "EXPORTED", "Exportiert"


class AppendOnlyError(Exception):
    def __init__(self) -> None:
        super().__init__("M-06: audit entries can only be appended, never changed")


class AuditEntry(BaseModel):
    # NULL actor means the system itself (e.g. the automatic escalation)
    actor = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.PROTECT, related_name="+"
    )
    action = models.CharField(max_length=32, choices=AuditAction.choices)
    risk = models.ForeignKey(
        "risks.Risk", null=True, blank=True, on_delete=models.PROTECT, related_name="audit_entries"
    )
    object_type = models.CharField(max_length=64)
    object_id = models.UUIDField()
    field = models.CharField(max_length=64, blank=True)
    old_value = models.TextField(blank=True)
    new_value = models.TextField(blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = "Audit-Eintrag"
        verbose_name_plural = "Audit-Log"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise AppendOnlyError
        super().save(*args, **kwargs)
