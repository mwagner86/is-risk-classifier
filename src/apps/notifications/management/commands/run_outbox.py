"""Worker: deliver queued notifications until stopped (container ``worker``)."""

import signal
import time
from argparse import ArgumentParser
from pathlib import Path
from types import FrameType
from typing import Any

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from apps.notifications.services import process_outbox

HEARTBEAT = Path("/tmp/outbox-heartbeat")  # noqa: S108 - container-local file for the healthcheck


class Command(BaseCommand):
    help = "Deliver pending notifications through the configured gateway."

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--interval", type=float, default=2.0, help="seconds between runs")
        parser.add_argument("--once", action="store_true", help="process one batch and exit")

    def handle(self, *args: Any, **options: Any) -> None:
        running = True

        def stop(signum: int, frame: FrameType | None) -> None:
            nonlocal running
            running = False

        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        self.stdout.write("outbox worker started")
        while running:
            close_old_connections()
            sent = process_outbox()
            if sent:
                self.stdout.write(f"processed {sent} notification(s)")
            HEARTBEAT.touch()
            if options["once"]:
                break
            time.sleep(options["interval"])
        self.stdout.write("outbox worker stopped")
