# Zugriffsmatrix: Ansicht → Rollen

Erzeugt mit `make access-matrix` aus `@allow_roles` und `@public` (M-05).
Nicht von Hand ändern. Was hier nicht freigegeben ist, lehnt die Middleware ab.

Die Tabelle zeigt, wer eine Ansicht aufrufen darf, nicht welche Risiken sie liefert:
Risikomelder (`NUTZER`) sehen in Liste, Detailansicht und Dashboard nur ihre eigenen
Risiken (`visible_risks`).

| Ansicht | Pfad | `NUTZER` | `RISK_MANAGER` | `CISO` | `ADMIN` |
| --- | --- | --- | --- | --- | --- |
| `dashboard` | `/` | ✓ | ✓ | ✓ | ✓ |
| `escalation_list` | `/eskalationen/` | – | ✓ | ✓ | ✓ |
| `escalation_resend` | `/eskalationen/<uuid:pk>/erneut-senden/` | – | – | – | ✓ |
| `risk_list` | `/risiken/` | ✓ | ✓ | ✓ | ✓ |
| `risk_create` | `/risiken/neu/` | ✓ | ✓ | – | – |
| `classification_preview` | `/risiken/kategorie-vorschau/` | ✓ | ✓ | – | – |
| `score_preview` | `/risiken/score-vorschau/` | – | ✓ | – | – |
| `risk_detail` | `/risiken/<uuid:pk>/` | ✓ | ✓ | ✓ | ✓ |
| `risk_edit` | `/risiken/<uuid:pk>/bearbeiten/` | ✓ | ✓ | – | – |
| `risk_reclassify` | `/risiken/<uuid:pk>/klassifizierung/` | – | ✓ | – | – |
| `risk_score` | `/risiken/<uuid:pk>/bewertung/` | – | ✓ | – | – |
| `risk_change_status` | `/risiken/<uuid:pk>/status/` | ✓ | ✓ | ✓ | – |
| `risk_incident_response` | `/risiken/<uuid:pk>/incident-response/` | – | ✓ | ✓ | – |
| `approval_list` | `/freigaben/` | – | ✓ | – | – |
| `approval_decide` | `/freigaben/<uuid:pk>/` | – | ✓ | – | – |
| `asset_list` | `/assets/` | ✓ | ✓ | ✓ | ✓ |
| `export_page` | `/export/` | – | ✓ | – | – |
| `export_csv` | `/export/csv/` | – | ✓ | – | – |
| `export_pdf` | `/export/pdf/` | – | ✓ | – | – |
| `audit_log` | `/audit-log/` | – | ✓ | ✓ | ✓ |

Öffentlich, ohne Anmeldung: `healthz` (`/healthz`), `login_failed` (`/anmeldung-abgelehnt/`), `oidc_authentication_init` (`/oidc/authenticate/`), `oidc_authentication_callback` (`/oidc/callback/`), `oidc_logout` (`/oidc/logout/`), `set_language` (`/sprache/`).
