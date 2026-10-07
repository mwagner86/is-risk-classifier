"""Small inline SVG icons (own drawings, stroke style). Decorative unless a label is given."""

from django import template
from django.utils.html import format_html
from django.utils.safestring import SafeString, mark_safe

register = template.Library()

PATHS = {
    "grid": (
        '<rect x="3" y="3" width="7" height="7" rx="1"/>'
        '<rect x="14" y="3" width="7" height="7" rx="1"/>'
        '<rect x="3" y="14" width="7" height="7" rx="1"/>'
        '<rect x="14" y="14" width="7" height="7" rx="1"/>'
    ),
    "list": (
        '<path d="M8 6h13M8 12h13M8 18h13"/>'
        '<circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>'
    ),
    "server": (
        '<rect x="3" y="4" width="18" height="7" rx="2"/>'
        '<rect x="3" y="13" width="18" height="7" rx="2"/>'
        '<path d="M7 7.5h.01M7 16.5h.01"/>'
    ),
    "alert": '<path d="M12 3 2 20h20L12 3z"/><path d="M12 10v4M12 17h.01"/>',
    "check": '<circle cx="12" cy="12" r="9"/><path d="m8 12 3 3 5-6"/>',
    "shield": '<path d="M12 3 4 6v6c0 4.5 3.4 8.2 8 9 4.6-.8 8-4.5 8-9V6l-8-3z"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "logout": '<path d="M15 4h4v16h-4M10 8l-4 4 4 4M6 12h10"/>',
}


@register.simple_tag
def icon(name: str, label: str = "", size: int = 18) -> SafeString:
    paths = mark_safe(PATHS[name])  # noqa: S308 - constant markup from this module
    if label:
        return format_html(
            '<svg role="img" aria-label="{}" width="{}" height="{}" viewBox="0 0 24 24" '
            'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
            'stroke-linejoin="round">'
            "<title>{}</title>{}</svg>",
            label,
            size,
            size,
            label,
            paths,
        )
    return format_html(
        '<svg aria-hidden="true" focusable="false" width="{}" height="{}" viewBox="0 0 24 24" '
        'fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round">{}</svg>',
        size,
        size,
        paths,
    )
