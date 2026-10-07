"""Risk levels for badges and the matrix. Bands as in the threat model of ESS hand-in 1:
critical from 20 (escalation threshold), high from 12 (counter-measure mandatory), medium from 6."""

from django.db import models
from django.db.models import Q


class RiskLevel(models.TextChoices):
    CRITICAL = "critical", "kritisch"
    HIGH = "high", "hoch"
    MEDIUM = "medium", "mittel"
    LOW = "low", "niedrig"


# Lower bound of each band, highest first
BANDS: tuple[tuple[int, RiskLevel], ...] = (
    (20, RiskLevel.CRITICAL),
    (12, RiskLevel.HIGH),
    (6, RiskLevel.MEDIUM),
    (1, RiskLevel.LOW),
)


def level_for(score: int | None) -> RiskLevel | None:
    if score is None:
        return None
    for lower, level in BANDS:
        if score >= lower:
            return level
    return None


def score_filter(level: RiskLevel, field: str = "assessment__score") -> Q:
    """Query for all scores inside ``level``'s band."""
    bounds = [lower for lower, _ in BANDS]
    index = [lvl for _, lvl in BANDS].index(level)
    query = Q(**{f"{field}__gte": bounds[index]})
    if index > 0:
        query &= Q(**{f"{field}__lt": bounds[index - 1]})
    return query
