"""Risk register: risk, its assessment and the CIA flags (class model of ESA 2).

The category is an enum attribute of the assessment, not a subclass (composition over
inheritance), so re-classification works at runtime. The price is that disjointness (INV-02)
cannot come from the type system: it is enforced by the field choices and a check constraint.
"""

from typing import Any

from django.db import models
from django.db.models import F, Q

from apps.core.models import BaseModel

ESCALATION_THRESHOLD = 20
SCALE_MIN, SCALE_MAX = 1, 5


class RiskStatus(models.TextChoices):
    DRAFT = "DRAFT", "Entwurf"
    CATEGORIZED = "CATEGORIZED", "Kategorisiert"
    SCORED = "SCORED", "Bewertet"
    ESCALATED = "ESCALATED", "Eskaliert"
    VALIDATED = "VALIDATED", "Validiert"
    CLOSED = "CLOSED", "Geschlossen"
    OBSOLETE = "OBSOLETE", "Obsolet"


class RiskCategory(models.TextChoices):
    """INV-02: exactly these two values, never both, never a third."""

    IS_RISIKO = "IS_RISIKO", "IS-Risiko"
    IT_RISIKO = "IT_RISIKO", "Allgemeines IT-Risiko"


class Origin(models.TextChoices):
    TECHNICAL_FAILURE = "TECHNICAL_FAILURE", "Technisches Versagen / Verschleiß"
    DELIBERATE_ATTACK = "DELIBERATE_ATTACK", "Vorsätzlicher Angriff"
    HUMAN_ERROR = "HUMAN_ERROR", "Menschliches Versehen"
    ENVIRONMENTAL = "ENVIRONMENTAL", "Umwelt / höhere Gewalt"
    UNKNOWN = "UNKNOWN", "Unbekannt"


class Risk(BaseModel):
    title = models.CharField("Titel", max_length=200)
    description = models.TextField("Beschreibung")
    status = models.CharField(max_length=16, choices=RiskStatus.choices, default=RiskStatus.DRAFT)
    reporter = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="reported_risks"
    )
    # Re-evaluation (CLOSED -> OBSOLETE) creates a new DRAFT that points back here
    predecessor = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="successor"
    )
    incident_response = models.TextField("Dokumentierte Incident Response", blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = "Risiko"
        verbose_name_plural = "Risiken"
        constraints = [
            models.CheckConstraint(
                condition=Q(status__in=RiskStatus.values), name="risk_status_valid"
            )
        ]

    def __str__(self) -> str:
        return self.title


class RiskAssessment(BaseModel):
    risk = models.OneToOneField(Risk, on_delete=models.PROTECT, related_name="assessment")
    origin = models.CharField("Ursprung", max_length=32, choices=Origin.choices, blank=True)
    # Effective category; NULL only while the risk is a DRAFT
    category = models.CharField(  # noqa: DJ001 - NULL means "not yet categorised", not a third value
        "Kategorie", max_length=16, choices=RiskCategory.choices, null=True, blank=True
    )
    probability = models.PositiveSmallIntegerField("Eintrittswahrscheinlichkeit", null=True)
    impact = models.PositiveSmallIntegerField("Schadensausmaß", null=True)
    score = models.PositiveSmallIntegerField("Risikowert", null=True, editable=False)
    assets = models.ManyToManyField("cmdb.Asset", blank=True, related_name="assessments")

    class Meta(BaseModel.Meta):
        verbose_name = "Risikobewertung"
        verbose_name_plural = "Risikobewertungen"
        constraints = [
            models.CheckConstraint(
                condition=Q(category__isnull=True) | Q(category__in=RiskCategory.values),
                name="assessment_category_is_or_it",
            ),
            models.CheckConstraint(
                condition=Q(origin="") | Q(origin__in=Origin.values),
                name="assessment_origin_valid",
            ),
            models.CheckConstraint(
                condition=Q(probability__isnull=True)
                | Q(probability__gte=SCALE_MIN, probability__lte=SCALE_MAX),
                name="assessment_probability_1_to_5",
            ),
            models.CheckConstraint(
                condition=Q(impact__isnull=True) | Q(impact__gte=SCALE_MIN, impact__lte=SCALE_MAX),
                name="assessment_impact_1_to_5",
            ),
            # The stored score is always P x I, or empty while either factor is missing
            models.CheckConstraint(
                condition=(
                    (Q(probability__isnull=True) | Q(impact__isnull=True)) & Q(score__isnull=True)
                )
                | Q(score=F("probability") * F("impact")),
                name="assessment_score_is_product",
            ),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        # Keep the score derived; never trust a value set from outside
        self.score = (
            None
            if self.probability is None or self.impact is None
            else self.probability * self.impact
        )
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and {"probability", "impact"} & set(update_fields):
            kwargs["update_fields"] = {*update_fields, "score"}
        super().save(*args, **kwargs)


class CIATriad(BaseModel):
    """Affected protection goals; several may be set at once."""

    assessment = models.OneToOneField(RiskAssessment, on_delete=models.PROTECT, related_name="cia")
    confidentiality = models.BooleanField("Vertraulichkeit", default=False)
    integrity = models.BooleanField("Integrität", default=False)
    availability = models.BooleanField("Verfügbarkeit", default=False)

    class Meta(BaseModel.Meta):
        verbose_name = "CIA-Triade"
        verbose_name_plural = "CIA-Triaden"

    @property
    def any_affected(self) -> bool:
        return self.confidentiality or self.integrity or self.availability


class ApprovalKind(models.TextChoices):
    CATEGORY_TO_IT = "CATEGORY_TO_IT", "Einordnung als IT-Risiko"
    SCORE_DOWNGRADE = "SCORE_DOWNGRADE", "Herabstufung unter 20"


class ApprovalState(models.TextChoices):
    PENDING = "PENDING", "Offen"
    APPROVED = "APPROVED", "Freigegeben"
    REJECTED = "REJECTED", "Abgelehnt"
    # Superseded by a later change (e.g. reclassified as IS risk); no decision was taken
    WITHDRAWN = "WITHDRAWN", "Zurückgezogen"


class ApprovalRequest(BaseModel):
    """A pending relaxation under M-04. Until approved, the stricter classification applies."""

    risk = models.ForeignKey(Risk, on_delete=models.PROTECT, related_name="approval_requests")
    kind = models.CharField(max_length=32, choices=ApprovalKind.choices)
    proposed_category = models.CharField(  # noqa: DJ001 - only set for CATEGORY_TO_IT
        max_length=16, choices=RiskCategory.choices, null=True, blank=True
    )
    proposed_probability = models.PositiveSmallIntegerField(null=True, blank=True)
    proposed_impact = models.PositiveSmallIntegerField(null=True, blank=True)
    state = models.CharField(
        max_length=16, choices=ApprovalState.choices, default=ApprovalState.PENDING
    )
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.PROTECT, related_name="requested_approvals"
    )
    decided_by = models.ForeignKey(
        "accounts.User",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="decided_approvals",
    )
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta(BaseModel.Meta):
        verbose_name = "Freigabeantrag"
        verbose_name_plural = "Freigabeanträge"
        constraints = [
            # M-04: nobody approves their own request
            models.CheckConstraint(
                condition=~Q(decided_by=F("requested_by")), name="approval_four_eyes"
            ),
            models.CheckConstraint(
                condition=(
                    Q(state=ApprovalState.PENDING, decided_by__isnull=True, decided_at__isnull=True)
                    | Q(
                        state=ApprovalState.WITHDRAWN,
                        decided_by__isnull=True,
                        decided_at__isnull=False,
                    )
                    | (
                        Q(state__in=[ApprovalState.APPROVED, ApprovalState.REJECTED])
                        & Q(decided_by__isnull=False, decided_at__isnull=False)
                    )
                ),
                name="approval_decision_complete",
            ),
        ]
