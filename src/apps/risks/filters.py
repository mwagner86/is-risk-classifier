"""Filter of the risk list, shared by the list page and the export (M-07: export only filtered)."""

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from urllib.parse import urlencode

from django.db.models import QuerySet

from apps.risks.levels import RiskLevel, score_filter
from apps.risks.models import Risk, RiskCategory, RiskStatus

SCALE = ("1", "2", "3", "4", "5")
# Attribute -> query parameter
PARAMS = {
    "status": "status",
    "category": "category",
    "level": "level",
    "probability": "p",
    "impact": "i",
}


@dataclass(frozen=True)
class RiskFilter:
    status: str = ""
    category: str = ""
    level: str = ""
    probability: str = ""
    impact: str = ""

    @classmethod
    def from_query(cls, params: Mapping[str, str]) -> "RiskFilter":
        """Keep only known values; anything else counts as "not set"."""

        def pick(key: str, allowed: list[str] | tuple[str, ...]) -> str:
            value = params.get(key, "")
            return value if value in allowed else ""

        return cls(
            status=pick("status", RiskStatus.values),
            category=pick("category", RiskCategory.values),
            level=pick("level", RiskLevel.values),
            probability=pick("p", SCALE),
            impact=pick("i", SCALE),
        )

    @property
    def is_empty(self) -> bool:
        return not any(asdict(self).values())

    def apply(self, risks: QuerySet[Risk]) -> QuerySet[Risk]:
        if self.status:
            risks = risks.filter(status=self.status)
        if self.category:
            risks = risks.filter(assessment__category=self.category)
        if self.level:
            risks = risks.filter(score_filter(RiskLevel(self.level)))
        if self.probability:
            risks = risks.filter(assessment__probability=int(self.probability))
        if self.impact:
            risks = risks.filter(assessment__impact=int(self.impact))
        return risks

    def describe(self) -> str:
        parts = []
        if self.status:
            parts.append(f"Status: {RiskStatus(self.status).label}")
        if self.category:
            parts.append(f"Kategorie: {RiskCategory(self.category).label}")
        if self.level:
            parts.append(f"Risikostufe: {RiskLevel(self.level).label}")
        if self.probability:
            parts.append(f"P = {self.probability}")
        if self.impact:
            parts.append(f"I = {self.impact}")
        return "; ".join(parts) or "ohne Filter"

    def query_string(self) -> str:
        return urlencode({PARAMS[k]: v for k, v in asdict(self).items() if v})
