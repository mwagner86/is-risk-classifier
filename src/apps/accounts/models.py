from typing import Any, ClassVar

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

from apps.core.models import BaseModel, NonDeletingQuerySet


class Role(models.TextChoices):
    """Roles from the class model (ESA 2). Values double as Keycloak group names."""

    NUTZER = "NUTZER", "Risikomelder"
    RISK_MANAGER = "RISK_MANAGER", "Risk Manager"
    CISO = "CISO", "CISO"
    ADMIN = "ADMIN", "Administration"


class AppUserManager(UserManager.from_queryset(NonDeletingQuerySet)):  # type: ignore[misc]
    pass


class User(BaseModel, AbstractUser):
    """Account mirrored from the identity provider on every login.

    Users are never deleted (they are authors in the audit log); leaving the company means
    ``is_active = False`` in the identity provider.
    """

    # NULL rather than "" so the unique constraint does not collide before the first login
    oidc_subject = models.CharField(max_length=255, unique=True, null=True, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices)

    objects: ClassVar[Any] = AppUserManager()

    class Meta:
        constraints = [
            models.CheckConstraint(condition=models.Q(role__in=Role.values), name="user_role_valid")
        ]

    def __str__(self) -> str:
        return self.username
