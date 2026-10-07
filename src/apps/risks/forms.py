"""Forms only collect input; every rule is checked again in ``apps.risks.services``."""

from typing import Any

from django import forms

from apps.cmdb.models import Asset
from apps.core.forms import style_widgets
from apps.risks.classification import categorize
from apps.risks.models import Origin, RiskCategory

ASSETS_LOCKED_HINT = "Wird freigeschaltet, sobald das Risiko als IS-Risiko eingestuft ist."


class ClassificationForm(forms.Form):
    confidentiality = forms.BooleanField(label="Vertraulichkeit", required=False)
    integrity = forms.BooleanField(label="Integrität", required=False)
    availability = forms.BooleanField(label="Verfügbarkeit", required=False)
    origin = forms.ChoiceField(
        label="Ursprung", choices=[("", "– bitte wählen –"), *Origin.choices], required=False
    )
    assets = forms.ModelMultipleChoiceField(
        label="Betroffene Assets", queryset=Asset.objects.all(), required=False
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        style_widgets(self)
        # Lock or unlock the assets field for the category the current input yields (AK-01.1)
        assets = self.fields["assets"]
        if self.computed_category == RiskCategory.IS_RISIKO:
            # Shown as mandatory; enforced by the service on submit, not on "Entwurf ablegen"
            assets.widget.attrs["required"] = True
        else:
            assets.disabled = True
            assets.help_text = ASSETS_LOCKED_HINT

    def _value(self, name: str) -> Any:
        return self[name].value() if self.is_bound else self.initial.get(name)

    @property
    def computed_category(self) -> RiskCategory | None:
        bool_field = forms.BooleanField(required=False)
        return categorize(
            bool_field.clean(self._value("confidentiality")),
            bool_field.clean(self._value("integrity")),
            bool_field.clean(self._value("availability")),
            self._value("origin") or "",
        )

    def classification(self) -> dict[str, Any]:
        data = self.cleaned_data
        return {
            "confidentiality": data["confidentiality"],
            "integrity": data["integrity"],
            "availability": data["availability"],
            "origin": data["origin"],
            "assets": list(data.get("assets") or []),
        }

    def add_service_errors(self, errors: dict[str, list[str]]) -> None:
        for field, messages in errors.items():
            # The protection goals are one question; show it at the first checkbox
            target = "confidentiality" if field == "cia" else field
            for message in messages:
                self.add_error(target if target in self.fields else None, message)


class RiskForm(ClassificationForm):
    title = forms.CharField(label="Titel", max_length=200, required=False)
    description = forms.CharField(label="Beschreibung", widget=forms.Textarea, required=False)

    field_order = [
        "title",
        "description",
        "confidentiality",
        "integrity",
        "availability",
        "origin",
        "assets",
    ]


def _scale_field(label: str, message: str) -> forms.IntegerField:
    return forms.IntegerField(
        label=label,
        min_value=1,
        max_value=5,
        # One message for empty, non-numeric and out-of-range input, naming the dimension
        error_messages={key: message for key in ("required", "invalid", "min_value", "max_value")},
        widget=forms.NumberInput(attrs={"step": 1, "inputmode": "numeric"}),
    )


class ScoreForm(forms.Form):
    probability = _scale_field(
        "Eintrittswahrscheinlichkeit",
        "Zulässiger Wertebereich für die Eintrittswahrscheinlichkeit ist 1 bis 5",
    )
    impact = _scale_field(
        "Schadensausmaß", "Zulässiger Wertebereich für das Schadensausmaß ist 1 bis 5"
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        style_widgets(self)

    def preview(self) -> int | None:
        """R = P x I for the live preview, None while not computable."""
        if not self.is_bound or not self.is_valid():
            return None
        return int(self.cleaned_data["probability"]) * int(self.cleaned_data["impact"])


class IncidentResponseForm(forms.Form):
    incident_response = forms.CharField(
        label="Dokumentierte Incident Response", widget=forms.Textarea, required=False
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        style_widgets(self)
