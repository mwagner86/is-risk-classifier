from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString

from apps.risks.levels import level_for

register = template.Library()


@register.simple_tag
def level_badge(score: int | None) -> SafeString:
    """Coloured badge with the level in words, so colour is never the only signal."""
    level = level_for(score)
    if level is None:
        return format_html('<span class="badge badge-none">{}</span>', "nicht bewertet")
    return format_html('<span class="badge badge-{}">{} {}</span>', level.value, score, level.label)
