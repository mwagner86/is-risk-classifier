"""Record of every export (M-07); the audit entry points here."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class ExportFormat(models.TextChoices):
    CSV = "csv", _("CSV")
    PDF = "pdf", _("PDF")


class Export(BaseModel):
    exported_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="exports"
    )
    format = models.CharField(max_length=8, choices=ExportFormat.choices)
    filter_description = models.CharField(max_length=500)
    query = models.CharField(max_length=500)
    row_count = models.PositiveIntegerField()

    class Meta(BaseModel.Meta):
        verbose_name = _("Export")
        verbose_name_plural = _("Exporte")
