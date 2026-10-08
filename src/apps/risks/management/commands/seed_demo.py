"""Fill an empty register with demo data for development (``make dev``, ``make seed``)."""

from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.keycloak import AccountError, fetch_claims, sync_users
from apps.risks.demo import DEMO_USERNAMES, seed
from apps.risks.models import Risk


class Command(BaseCommand):
    help = "Create demo risks for the Keycloak demo accounts; does nothing if risks exist."

    def handle(self, *args: Any, **options: Any) -> None:
        # Development only: the runtime image runs with DEBUG off (make prod, production)
        if not settings.DEBUG:
            raise CommandError("seed_demo runs only with DJANGO_DEBUG=true")
        if Risk.objects.exists():
            self.stdout.write("Demo data skipped: the register is not empty (see make reset).")
            return
        try:
            users = sync_users(fetch_claims(DEMO_USERNAMES))
        except (AccountError, ImproperlyConfigured, OSError) as exc:  # URLError is an OSError
            raise CommandError(f"Demo accounts from Keycloak: {exc}") from exc
        count = seed(users)
        self.stdout.write(self.style.SUCCESS(f"Demo data: {count} risks created."))
