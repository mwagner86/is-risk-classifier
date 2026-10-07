"""US-01: the categorisation rule, kept free of database access so it can be tested exhaustively."""

from apps.risks.models import Origin, RiskCategory


def categorize(
    confidentiality: bool, integrity: bool, availability: bool, origin: str
) -> RiskCategory | None:
    """Return the category the rule yields, or None while protection goal or origin is missing.

    - confidentiality or integrity affected -> IS risk, whatever the origin (AK-01.1)
    - only availability, origin technical failure / wear -> general IT risk (AK-01.2)
    - only availability, any other origin -> IS risk
    """
    if not (confidentiality or integrity or availability) or not origin:
        return None
    if confidentiality or integrity:
        return RiskCategory.IS_RISIKO
    if origin == Origin.TECHNICAL_FAILURE:
        return RiskCategory.IT_RISIKO
    return RiskCategory.IS_RISIKO
