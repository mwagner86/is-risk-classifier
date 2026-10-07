"""Rows of the export, shared by CSV and PDF, and the CSV writer."""

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from apps.accounts.models import User
from apps.risks.levels import level_for
from apps.risks.models import Risk

CSV_COLUMNS = (
    _("Kennung"),
    _("Titel"),
    _("Beschreibung"),
    _("Kategorie"),
    _("Status"),
    _("Vertraulichkeit"),
    _("Integrität"),
    _("Verfügbarkeit"),
    _("Ursprung"),
    _("Eintrittswahrscheinlichkeit"),
    _("Schadensausmaß"),
    _("Risikowert"),
    _("Risikostufe"),
    _("Assets"),
    _("Erfasst am"),
    _("Erfasst von"),
    # M-08: every row names who exported it and when
    _("Exportiert von"),
    _("Exportiert am"),
)
# Leading characters that make spreadsheet programs evaluate a cell (CWE-1236, T-04)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def exporter_label(user: User) -> str:
    name = user.get_full_name()
    return f"{name} ({user.username})" if name else user.username


def stamp(moment: datetime) -> str:
    """Date and time in the active language (de: 07.10.2026 09:20, en: 2026-10-07 09:20)."""
    return date_format(timezone.localtime(moment), "SHORT_DATETIME_FORMAT")


def neutralise(value: str) -> str:
    """Prefix a would-be formula with an apostrophe so it is shown as text (OWASP)."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def _yes(flag: bool) -> str:
    return str(_("ja") if flag else _("nein"))


def risk_record(risk: Risk) -> dict[str, Any]:
    assessment = risk.assessment
    cia = assessment.cia
    goals = [
        label
        for flag, label in (
            (cia.confidentiality, _("Vertraulichkeit")),
            (cia.integrity, _("Integrität")),
            (cia.availability, _("Verfügbarkeit")),
        )
        if flag
    ]
    level = level_for(assessment.score)
    return {
        "id": str(risk.pk),
        "title": risk.title,
        "description": risk.description,
        "category": str(assessment.get_category_display() or ""),
        "status": str(risk.get_status_display()),
        "confidentiality": cia.confidentiality,
        "integrity": cia.integrity,
        "availability": cia.availability,
        "goals": ", ".join(str(g) for g in goals),
        "origin": str(assessment.get_origin_display()) if assessment.origin else "",
        "probability": assessment.probability,
        "impact": assessment.impact,
        "score": assessment.score,
        "level": str(level.label) if level else "",
        "assets": ", ".join(f"{a.cmdb_key} {a.name}" for a in assessment.assets.all()),
        "created_at": stamp(risk.created_at),
        "reporter": risk.reporter.username,
    }


def to_csv(records: Iterable[dict[str, Any]], exporter: str, exported_at: str) -> bytes:
    """Semicolon-separated UTF-8 with BOM, as German spreadsheet programs expect it."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow([str(column) for column in CSV_COLUMNS])
    for r in records:
        cells: list[Any] = [
            r["id"],
            r["title"],
            r["description"],
            r["category"],
            r["status"],
            _yes(r["confidentiality"]),
            _yes(r["integrity"]),
            _yes(r["availability"]),
            r["origin"],
            r["probability"] or "",
            r["impact"] or "",
            r["score"] or "",
            r["level"],
            r["assets"],
            r["created_at"],
            r["reporter"],
            exporter,
            exported_at,
        ]
        writer.writerow([neutralise(c) if isinstance(c, str) else c for c in cells])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def pdf_payload(
    records: Iterable[dict[str, Any]],
    exporter: str,
    exported_at: str,
    filter_text: str,
    language: str | None = "de",
) -> dict[str, Any]:
    keys = (
        "id", "title", "description", "category", "status", "goals", "origin",
        "probability", "impact", "score", "level", "assets", "created_at",
    )  # fmt: skip
    return {
        "exported_by": exporter,
        "exported_at": exported_at,
        "filter": filter_text,
        "language": "en" if language == "en" else "de",
        "risks": [{key: r[key] for key in keys} for r in records],
    }
