"""Write the access matrix (route -> roles) as Markdown (``make access-matrix``, M-05)."""

from argparse import ArgumentParser
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand

from apps.core.access_matrix import render


class Command(BaseCommand):
    help = "Write docs/access-matrix.md from the @allow_roles/@public declarations."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--output", type=Path, default=Path("docs/access-matrix.md"))

    def handle(self, *args: Any, **options: Any) -> None:
        output: Path = options["output"]
        output.write_text(render(), encoding="utf-8")
        self.stdout.write(f"Access matrix written to {output}")
