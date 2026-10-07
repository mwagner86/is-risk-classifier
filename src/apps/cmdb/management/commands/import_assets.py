"""Import or update assets from a CMDB CSV export (columns: cmdb_key, name, criticality)."""

import csv
from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.cmdb.models import Asset

REQUIRED_COLUMNS = {"cmdb_key", "name", "criticality"}


class Command(BaseCommand):
    help = "Import assets from a CMDB CSV export; existing keys are updated, nothing is deleted."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("csv_path", type=Path)

    @transaction.atomic
    def handle(self, *args: Any, **options: Any) -> None:
        path: Path = options["csv_path"]
        if not path.is_file():
            raise CommandError(f"File not found: {path}")
        created = updated = 0
        with path.open(encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle)
            missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"Missing columns: {', '.join(sorted(missing))}")
            for line, row in enumerate(reader, start=2):
                try:
                    criticality = int(row["criticality"])
                except ValueError as exc:
                    raise CommandError(f"Line {line}: criticality must be a number") from exc
                asset = Asset.objects.filter(cmdb_key=row["cmdb_key"].strip()).first()
                is_new = asset is None
                if asset is None:
                    asset = Asset(cmdb_key=row["cmdb_key"].strip())
                asset.name = row["name"].strip()
                asset.criticality = criticality
                try:
                    asset.full_clean()
                except ValidationError as exc:
                    raise CommandError(f"Line {line}: {exc.message_dict}") from exc
                asset.save()
                created += is_new
                updated += not is_new
        self.stdout.write(f"Assets imported: {created} created, {updated} updated")
