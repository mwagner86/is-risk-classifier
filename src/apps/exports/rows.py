"""Rows of the export, shared by CSV and PDF, and the CSV writer."""

import csv
import io
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from django.utils import timezone

from apps.accounts.models import User
from apps.risks.levels import level_for
from apps.risks.models import Risk

CSV_COLUMNS = (
    "Kennung",
    "Titel",
    "Beschreibung",
    "Kategorie",
    "Status",
    "Vertraulichkeit",
    "Integrität",
    "Verfügbarkeit",
    "Ursprung",
    "Eintrittswahrscheinlichkeit",
    "Schadensausmaß",
    "Risikowert",
    "Risikostufe",
    "Assets",
    "Erfasst am",
    "Erfasst von",
    # M-08: every row names who exported it and when
    "Exportiert von",
    "Exportiert am",
)
# Leading characters that make spreadsheet programs evaluate a cell (CWE-1236, T-04)
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")
TIMESTAMP = "%d.%m.%Y %H:%M"


def exporter_label(user: User) -> str:
    name = user.get_full_name()
    return f"{name} ({user.username})" if name else user.username


def stamp(moment: datetime) -> str:
    return timezone.localtime(moment).strftime(TIMESTAMP)


def neutralise(value: str) -> str:
    """Prefix a would-be formula with an apostrophe so it is shown as text (OWASP)."""
    return f"'{value}" if value.startswith(FORMULA_PREFIXES) else value


def _yes(flag: bool) -> str:
    return "ja" if flag else "nein"


def risk_record(risk: Risk) -> dict[str, Any]:
    assessment = risk.assessment
    cia = assessment.cia
    goals = [
        label
        for flag, label in (
            (cia.confidentiality, "Vertraulichkeit"),
            (cia.integrity, "Integrität"),
            (cia.availability, "Verfügbarkeit"),
        )
        if flag
    ]
    level = level_for(assessment.score)
    return {
        "id": str(risk.pk),
        "title": risk.title,
        "description": risk.description,
        "category": assessment.get_category_display() or "",
        "status": risk.get_status_display(),
        "confidentiality": cia.confidentiality,
        "integrity": cia.integrity,
        "availability": cia.availability,
        "goals": ", ".join(goals),
        "origin": assessment.get_origin_display() if assessment.origin else "",
        "probability": assessment.probability,
        "impact": assessment.impact,
        "score": assessment.score,
        "level": level.label if level else "",
        "assets": ", ".join(f"{a.cmdb_key} {a.name}" for a in assessment.assets.all()),
        "created_at": stamp(risk.created_at),
        "reporter": risk.reporter.username,
    }


def to_csv(records: Iterable[dict[str, Any]], exporter: str, exported_at: str) -> bytes:
    """Semicolon-separated UTF-8 with BOM, as German spreadsheet programs expect it."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
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
    records: Iterable[dict[str, Any]], exporter: str, exported_at: str, filter_text: str
) -> dict[str, Any]:
    keys = (
        "id", "title", "description", "category", "status", "goals", "origin",
        "probability", "impact", "score", "level", "assets", "created_at",
    )  # fmt: skip
    return {
        "exported_by": exporter,
        "exported_at": exported_at,
        "filter": filter_text,
        "risks": [{key: r[key] for key in keys} for r in records],
    }
