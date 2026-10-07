"""Shared base for all domain models.

Identity and creation time live here once instead of per class (lecturer feedback on ESA 2:
"id nicht typspezifisch – rausabstrahieren"). Deletion is blocked on every path the ORM offers;
the database triggers from ``apps.core.db`` block the remaining ones (INV-03).
"""

import uuid
from typing import Any, NoReturn

from django.db import models
from django.utils import timezone


class DeletionForbiddenError(Exception):
    """Raised on any attempt to delete a domain record physically (INV-03)."""

    def __init__(self, model_name: str) -> None:
        super().__init__(
            f"INV-03: {model_name} records are never deleted; set the status to OBSOLETE instead"
        )


class NonDeletingQuerySet(models.QuerySet[Any]):
    def delete(self) -> NoReturn:
        raise DeletionForbiddenError(self.model.__name__)


class BaseModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    objects = NonDeletingQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ["-created_at"]

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise DeletionForbiddenError(type(self).__name__)
