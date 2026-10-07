"""Assets mirrored from the CMDB. They exist independently of risks and are read-only in the
app; the only write path is the ``import_assets`` command."""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class Asset(BaseModel):
    cmdb_key = models.CharField(_("CMDB-Kennung"), max_length=64, unique=True)
    name = models.CharField(max_length=200)
    criticality = models.PositiveSmallIntegerField(
        _("Kritikalität"), validators=[MinValueValidator(1), MaxValueValidator(5)]
    )

    class Meta(BaseModel.Meta):
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(criticality__gte=1, criticality__lte=5),
                name="asset_criticality_1_to_5",
            )
        ]

    def __str__(self) -> str:
        return f"{self.cmdb_key} {self.name}"
