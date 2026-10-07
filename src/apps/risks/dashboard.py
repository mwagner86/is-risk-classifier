"""Figures for the dashboard, always limited to the risks the user may see."""

from dataclasses import dataclass, field

from django.db.models import Count, Exists, OuterRef, QuerySet

from apps.accounts.models import Role, User
from apps.notifications.services import unresolved_failures
from apps.risks.levels import RiskLevel, level_for
from apps.risks.models import SCALE_MAX, SCALE_MIN, Risk, RiskCategory, RiskStatus
from apps.risks.services import visible_risks

OPEN_STATUSES = (
    RiskStatus.CATEGORIZED,
    RiskStatus.SCORED,
    RiskStatus.ESCALATED,
    RiskStatus.VALIDATED,
)
# Decision 7: the red flag is meant for these roles
FLAG_ROLES = frozenset({Role.RISK_MANAGER, Role.CISO, Role.ADMIN})


@dataclass(frozen=True)
class MatrixCell:
    probability: int
    impact: int
    count: int

    @property
    def level(self) -> RiskLevel | None:
        return level_for(self.probability * self.impact)


@dataclass(frozen=True)
class MatrixRow:
    probability: int
    cells: list[MatrixCell] = field(default_factory=list)


@dataclass(frozen=True)
class DashboardData:
    open_count: int
    is_count: int
    it_count: int
    escalated_count: int
    failed_count: int
    show_failures: bool
    matrix: list[MatrixRow]
    failed_risks: list[Risk]
    recent_risks: list[Risk]


def _failure_exists() -> Exists:
    return Exists(unresolved_failures().filter(risk=OuterRef("pk")))


def with_failure_flag(risks: QuerySet[Risk]) -> QuerySet[Risk]:
    """Annotate ``notification_failed`` for the red flag in tables."""
    return risks.annotate(notification_failed=_failure_exists())


def only_failed(risks: QuerySet[Risk]) -> QuerySet[Risk]:
    return risks.filter(_failure_exists())


def dashboard_data(user: User) -> DashboardData:
    risks = with_failure_flag(visible_risks(user))
    open_risks = risks.filter(status__in=OPEN_STATUSES)
    per_category = dict(
        open_risks.values_list("assessment__category").annotate(n=Count("pk")).order_by()
    )
    counts = {
        (p, i): n
        for p, i, n in open_risks.filter(assessment__score__isnull=False)
        .values_list("assessment__probability", "assessment__impact")
        .annotate(n=Count("pk"))
        .order_by()
    }
    matrix = [
        MatrixRow(
            p, [MatrixCell(p, i, counts.get((p, i), 0)) for i in range(SCALE_MIN, SCALE_MAX + 1)]
        )
        for p in range(SCALE_MAX, SCALE_MIN - 1, -1)
    ]
    show_failures = user.role in FLAG_ROLES
    failed = list(only_failed(risks).order_by("-created_at")) if show_failures else []
    return DashboardData(
        open_count=open_risks.count(),
        is_count=per_category.get(RiskCategory.IS_RISIKO, 0),
        it_count=per_category.get(RiskCategory.IT_RISIKO, 0),
        escalated_count=risks.filter(status=RiskStatus.ESCALATED).count(),
        failed_count=len(failed),
        show_failures=show_failures,
        matrix=matrix,
        failed_risks=failed,
        recent_risks=list(open_risks.order_by("-created_at")[:10]),
    )
