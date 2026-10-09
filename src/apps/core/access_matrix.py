"""Route -> roles as a Markdown table, generated from ``@allow_roles`` and ``@public`` (M-05).

Written to docs/access-matrix.md by ``make access-matrix``; a test fails if the file is stale.
The table shows who may call a view, not which rows a view returns: reporters reach the list,
the detail page and the dashboard, but see only their own risks there (``visible_risks``).
"""

from collections.abc import Iterator

from django.urls import URLPattern, URLResolver, get_resolver

from apps.accounts.models import Role
from apps.core.access import declared_access

YES, NO = "✓", "–"


def _routes(resolver: URLResolver, prefix: str = "") -> Iterator[tuple[str, URLPattern]]:
    for entry in resolver.url_patterns:
        if isinstance(entry, URLResolver):
            yield from _routes(entry, prefix + str(entry.pattern))
        else:
            yield "/" + prefix + str(entry.pattern), entry


def render() -> str:
    roles = list(Role)
    protected, public = [], []
    for path, pattern in _routes(get_resolver()):
        access = declared_access(pattern.callback)
        if access is True:
            public.append(f"`{pattern.name}` (`{path}`)")
            continue
        allowed = access or frozenset()
        cells = " | ".join(YES if role in allowed else NO for role in roles)
        protected.append(f"| `{pattern.name}` | `{path}` | {cells} |")
    lines = [
        "# Zugriffsmatrix: Ansicht → Rollen",
        "",
        "Erzeugt mit `make access-matrix` aus `@allow_roles` und `@public` (M-05).",
        "Nicht von Hand ändern. Was hier nicht freigegeben ist, lehnt die Middleware ab.",
        "",
        "Die Tabelle zeigt, wer eine Ansicht aufrufen darf, nicht welche Risiken sie liefert:",
        "Risikomelder (`NUTZER`) sehen in Liste, Detailansicht und Dashboard nur ihre eigenen",
        "Risiken (`visible_risks`).",
        "",
        "| Ansicht | Pfad | " + " | ".join(f"`{role}`" for role in roles) + " |",
        "| --- | --- | " + " | ".join("---" for _ in roles) + " |",
        *protected,
        "",
        "Öffentlich, ohne Anmeldung: " + ", ".join(public) + ".",
    ]
    return "\n".join(lines) + "\n"
