# IS-Risk Classifier

[English](README.md) · **Deutsch**

Leichtgewichtiges Risikoregister: trennt IT-Risiken von Informationssicherheitsrisiken
(IS-Risiken) anhand von Schutzzielen und Ursprung, berechnet den Risikowert R = P × I und eskaliert
kritische IS-Risiken an das Incident-Response-Team.

> [!WARNING]
> **Studienprojekt, nicht für den Produktivbetrieb.** Der IS-Risk Classifier ist weder vollständig
> noch unabhängig geprüft. Er ist nicht für echte Risikodaten gedacht. Die Grenzen stehen unten.

## Herkunft, Zweck und Grenzen

**Herkunft.** Das Projekt ist im Studiengang IT-Sicherheit an der Technischen Hochschule
Brandenburg entstanden, für zwei Module:

- **Softwaretechnik** (Sommersemester 2026): Anforderungen als User Stories mit
  Abnahmekriterien (US-01 bis US-04, AK-xx.x) und das UML-Modell. Die fachliche Spezifikation
  stammt von dort.
- **Entwicklung sicherer Softwaresysteme** (Wintersemester 2026/27): Threat Analysis nach NIST
  SP 800-154 mit den Attack Vectors T-01 bis T-10 und den Security Controls M-01 bis M-10
  (Hand-in 1), daraus Sicherheitsanforderungen mit Testszenarien (Hand-in 2). Die Kennungen in Code
  und Tests (`@pytest.mark.req("M-05")`) beziehen sich auf diese Arbeiten.

**Zweck.** Die Anwendung ist der Gegenstand dieser Analysen. Sie zeigt, dass sich die Anforderungen
und Security Controls umsetzen und prüfen lassen. Für die Abnahmekriterien von US-01 bis US-03, die
Invarianten INV-02 und INV-03 und die Security Controls M-01 bis M-10 gibt es Tests, zugeordnet in
[`docs/traceability.md`](docs/traceability.md). Ein Produkt ist sie nicht.

**Entstehung.** Anforderungen, Modell, Analysen und Entscheidungen stammen aus den Studienarbeiten.
Der Code ist weitgehend mit Claude Code (Anthropic, Modell Claude Opus 5.5) erzeugt worden.

**Grenzen** (Stand 23.10.2026):

- **Kein Sicherheitsaudit.** Es gab weder ein Review noch einen Penetrationstest durch Dritte. Die
  Security Controls sind so gut wie die eigene Threat Analysis und ihre Tests.
- **Abhängigkeiten mit bekannten Vulnerabilities:** `make audit` meldete am 22.10.2026 Befunde in
  `pillow` 12.3.0 und `certifi` 2026.7.22. Behobene Versionen gibt es, eingespielt sind sie noch
  nicht.
- **Anmeldung nur für die Entwicklung:** Keycloak läuft mit Demo-Konten und gemeinsamem
  Demo-Passwort, ohne Zwei-Faktor-Anmeldung und ohne Passwortrichtlinie. Ohne vorgeschalteten
  TLS-Proxy läuft alles über HTTP auf `localhost`.
- **Offene Anforderungen aus Hand-in 2:** Die Administration sieht noch das ganze Register statt
  nur Kennung und Zustellstatus. Befunde der Abhängigkeitsprüfung lassen sich nicht mit Ablaufdatum
  zurückstellen. Ein Export ohne Treffer liefert eine leere Datei statt eines Hinweises.
- **Kein echter Versand:** `notify-gateway` ist ein Platzhalter. E-Mails landen in Mailpit, SMS nur
  im Log.
- **Keine laufende CI:** Der Workflow `.github/workflows/ci.yml` ist vorbereitet, GitHub Actions ist
  im Repository aber abgeschaltet. Dependabot läuft.
- **Beispieldaten:** Risiken, Assets und Konten sind erfunden.

## Start

Voraussetzung: Docker mit Compose und `make`. Alles andere läuft in Containern.

```bash
git clone https://github.com/mwagner86/is-risk-classifier.git && cd is-risk-classifier
```

```bash
make dev
```

Danach <http://localhost:8000> (oder <http://127.0.0.1:8000>) öffnen und mit einem der Demo-Konten
unten anmelden — nicht mit `admin`, das ist nur das Konto der Keycloak-Verwaltung. Beim ersten Start
legt `make dev` die Datei `.env` mit zufälligen Geheimnissen an. Das Passwort der Demo-Konten steht
dort unter `DEMO_USER_PASSWORD`:

```bash
grep ^DEMO_USER_PASSWORD= .env
```

| Konto | Rolle |
| --- | --- |
| `melder` | Risikomelder (NUTZER) |
| `rm.mueller`, `rm.schmidt` | Risk Manager — zwei, für das Vier-Augen-Prinzip (M-04) |
| `ciso` | CISO |
| `app-admin` | Administration |
| `ohne-rolle` | keine Rolle — die Anmeldung wird abgelehnt |

## Befehle

| Befehl | Wirkung |
| --- | --- |
| `make dev` | Stack bauen und starten (App, Worker, Stylesheet, PostgreSQL, Keycloak), leeres Register mit Beispieldaten füllen |
| `make seed` | Beispieldaten anlegen, nur wenn das Register leer ist (läuft auch in `make dev`) |
| `make css` | Stylesheet einmalig minifiziert bauen |
| `make prod` / `make prod-down` | produktionsnaher Stack: Laufzeit-Image mit gunicorn, Debug aus, schreibgeschützt |
| `make sbom` | SBOM im CycloneDX-Format nach `sbom/is-risk-classifier.cdx.json` |
| `make audit` | Laufzeit-Abhängigkeiten gegen bekannte Schwachstellen prüfen (pip-audit) |
| `make trace` | Nachweistabelle Anforderung → Tests nach `docs/traceability.md` |
| `make messages` | Oberflächentexte einsammeln, englische Übersetzungen eintragen, Katalog kompilieren |
| `make test` | Tests gegen PostgreSQL, Filter mit `make test ARGS="-k m_05"` |
| `make lint` | ruff (Lint und Format) und mypy (strict) |
| `make fmt` | Formatierung und sichere Korrekturen anwenden |
| `make migrations` | Migrationen nach Modelländerungen erzeugen |
| `make lock` | `uv.lock` nach Änderungen an `pyproject.toml` neu auflösen |
| `make logs` / `make down` | Logs verfolgen / Stack anhalten, Daten bleiben |
| `make reset` | Stack anhalten und **Datenbank- und Keycloak-Volumes löschen** |

Änderungen an `docker/keycloak/realm-is-risk.json` wirken erst nach `make reset`, weil Keycloak einen
vorhandenen Realm beim Import nicht überschreibt.

**Beispieldaten:** Ist das Register leer, legt `make dev` 13 Risiken an (`manage.py seed_demo`). Sie
decken alle Zustände ab, IS- und IT-Risiken, offene und entschiedene Freigaben, eine Eskalation mit
fehlgeschlagener Notifikation und ein obsoletes Risiko mit Nachfolger. Vier davon hat `melder`
erfasst. Angelegt wird über die Fachlogik, Audit-Log und Mails in Mailpit sind also echt. Die Konten
liest der Befehl aus Keycloak (Admin-API), damit ihre Kennung zur späteren Anmeldung passt. Er läuft
nur mit `DJANGO_DEBUG=true` und lässt ein Register mit Daten unangetastet. Neu anfangen:
`make reset`, dann `make dev`.

## Aufbau

| Dienst | Aufgabe | Erreichbar |
| --- | --- | --- |
| `web` | Django-Anwendung | `127.0.0.1:8000` |
| `worker` | verschickt Notifikationen aus der Warteschlange über `notify-gateway` | — |
| `notify-gateway` | Platzhalter für den externen E-Mail-/SMS-Anbieter: E-Mail an Mailpit, SMS ins Log; Ausfall per `NOTIFY_FAILURE_MODE` erzwingbar | nur `worker` |
| `mailpit` | fängt alle E-Mails ab, Weboberfläche | `127.0.0.1:8025` |
| `css` | baut das Stylesheet mit dem Tailwind-CLI neu, sobald sich Templates ändern | — |
| `pdf-renderer` | erzeugt die PDF-Exporte; eigener Prozess ohne Datenbanknetz und ohne Zugangsdaten, Dateisystem schreibgeschützt | nur `web` |
| `keycloak` | Identity Provider (OIDC mit PKCE), Rollen aus Gruppen | `127.0.0.1:8080` |
| `migrate` | einmalig als Datenbank-Eigentümer: Migrationen, eingeschränkte Anwendungsrolle, CMDB-Beispieldaten | — |
| `db` | PostgreSQL, im internen Netz ohne Route nach außen | nur `web`, `worker`, `migrate` |
| `test`, `tools` | Testlauf, Lint, Lockfile (Profil `tools`) | — |

```text
├── src/                    Anwendungscode (auf PYTHONPATH)
│   ├── manage.py
│   ├── config/             Einstellungen, URLs, WSGI
│   ├── apps/
│   │   ├── core/           Basismodell (UUID, Zeitstempel, kein Löschen), Zugriffsschutz, DB-Trigger
│   │   ├── accounts/       Benutzer, Rollen, Anmeldung über Keycloak
│   │   ├── risks/          Risiko, Bewertung, CIA-Triade, Freigabeanträge, Zustandsmaschine
│   │   ├── cmdb/           Assets, CSV-Import, Beispieldaten
│   │   ├── notifications/  Notifikationen: Warteschlange, HttpGateway (und Mock für Tests), Worker
│   │   ├── exports/        CSV- und PDF-Export (gefiltert, gekennzeichnet)
│   │   └── audit/          Audit-Log, nur anfügbar, und seine Ansicht
│   ├── pdf_renderer/       eigenständiger PDF-Dienst ohne Django und ohne Datenbanktreiber
│   ├── notify_gateway/     eigenständiger Benachrichtigungsdienst (Platzhalter für den Anbieter)
│   └── templates/
├── tests/                  pytest; jeder Test trägt seine Anforderung: @pytest.mark.req("M-05")
│   ├── assets/             Tailwind-Quelle mit den Design-Tokens (wird nicht ausgeliefert)
├── tools/                  SBOM-Erzeugung
├── docker/                 Dockerfile (dev, runtime), Keycloak-Realm
├── docs/                   Spezifikation, Screenshots, Nachweistabelle
└── Makefile, compose.yaml, compose.prod.yaml, pyproject.toml, uv.lock, .env.example
```

## Oberfläche

Dunkles Thema nach dem Stil von dependencytrack.org, auf Deutsch (Standard) und Englisch. Die
Aufnahmen zeigen die englische Oberfläche mit Beispieldaten; Asset-Namen kommen aus der deutschen
CMDB-Beispieldatei und bleiben deshalb deutsch.

### Dashboard

![Dashboard: Kennzahlen, Risikomatrix, rot markierte Eskalation](docs/screenshots/en/01-dashboard.png)

Kennzahlen, Risikomatrix 5 × 5 (ein Klick auf eine Zelle filtert die Risikoliste) und Badges je
Risikostufe: ab 20 kritisch, 12–19 hoch, 6–11 mittel, 1–5 niedrig. Ein Risiko, dessen Eskalation
das Incident-Response-Team nicht erreicht hat, bleibt rot markiert, mit Symbol und Text, bis eine
erneute Zustellung gelingt (AK-03.3).

### Risiko erfassen (US-01)

![Erfassungsformular mit Live-Einstufung](docs/screenshots/en/03-report-risk.png)

Die Einstufung erscheint schon beim Ausfüllen. Hier: nur Verfügbarkeit und technisches Versagen
ergeben ein IT-Risiko, das erst nach Freigabe durch einen Risk Manager wirksam wird (M-04); das Feld
„Affected assets“ bleibt gesperrt, bis die Eingaben ein IS-Risiko ergeben.

### Risiko im Detail

![Detailseite mit fehlgeschlagener Notifikation und Verlauf](docs/screenshots/en/04-risk-detail.png)

Bewertung, Aktionen je Rolle, Notifikationen mit Zustellstatus und der Verlauf aus dem Audit-Log.

### Bewerten (US-02)

![Bewertung mit Fehlermeldung zum Schadensausmaß](docs/screenshots/en/05-scoring-validation.png)

Werte außerhalb von 1 bis 5 weist der Server ab; die Meldung nennt die Dimension, der Risikowert
zeigt „Cannot be calculated“.

### Weitere Seiten

| | |
| --- | --- |
| ![Risikoliste mit Filtern](docs/screenshots/en/02-risks.png) | ![Freigaben nach dem Vier-Augen-Prinzip](docs/screenshots/en/06-approvals.png) |
| Risikoliste mit Filtern | Freigaben: Anträge anderer, nie die eigenen (M-04) |
| ![Eskalationen mit „Resend“ für die Administration](docs/screenshots/en/07-escalations.png) | ![Export nur mit Filter](docs/screenshots/en/08-export.png) |
| Eskalationen: erneut senden nur durch die Administration | Export nur mit Filter, jede Datei gekennzeichnet (M-07, M-08) |
| ![Audit-Log](docs/screenshots/en/09-audit-log.png) | ![Anmeldung über Keycloak auf Englisch](docs/screenshots/en/10-sign-in.png) |
| Audit-Log, nur anfügbar (M-06) | Anmeldung über Keycloak in der gewählten Sprache |
| ![Dashboard auf dem Handy](docs/screenshots/en/11-dashboard-mobile.png) | ![Eskalationsmail in Mailpit](docs/screenshots/en/12-mailpit.png) |
| Dashboard auf dem Handy | Eskalationsmail in Mailpit: nur Kennung und Link (M-09) |

Ein PDF-Export auf Englisch liegt als Beispiel unter
[`docs/screenshots/en/export-example.pdf`](docs/screenshots/en/export-example.pdf).

## Sprache

Umgeschaltet wird oben rechts mit **DE** / **EN**. Die Wahl bleibt in einem Cookie gespeichert; ohne
Wahl entscheidet die Sprache des Browsers. Die Anmeldeseite von Keycloak folgt der gewählten Sprache,
CSV- und PDF-Exporte ebenfalls. Deutsch ist die Quellsprache: Die Meldungen der Spezifikation stehen
dort wörtlich. Die Benachrichtigungen an das Incident-Response-Team bleiben deutsch.

![Dashboard auf Deutsch](docs/screenshots/de/dashboard.png)

## Ablauf ausprobieren

1. Als `melder` ein Risiko erfassen. Wer nur „Verfügbarkeit“ und „Technisches Versagen /
   Verschleiß“ wählt, bekommt einen Antrag auf IT-Einordnung; bis zur Freigabe gilt das Risiko als
   IS-Risiko (M-04).
2. Als `rm.mueller` unter **Risiken** bewerten. Ein IS-Risiko ab 20 wird sofort eskaliert; die
   E-Mail an das Incident-Response-Team erscheint in Mailpit (<http://localhost:8025>), die SMS im
   Log des Gateways (`docker compose logs notify-gateway`). Sie enthält nur Kennung und Link (M-09).
3. Als `rm.schmidt` (oder `rm.mueller` für Anträge anderer) unter **Freigaben** entscheiden.
4. Als Risk Manager unter **Export** filtern und als CSV oder PDF exportieren. Ohne Filter wird
   nicht exportiert; jeder Export erscheint im **Audit-Log**.
5. Gateway-Ausfall (AK-03.3) nachstellen: in `.env` `NOTIFY_FAILURE_MODE=timeout` (oder `5xx`)
   setzen, `docker compose up -d notify-gateway`, dann ein IS-Risiko mit 4 × 5 bewerten. Das Risiko
   bleibt rot markiert. Nach `NOTIFY_FAILURE_MODE=none` und erneutem `docker compose up -d
   notify-gateway` stellt `app-admin` unter **Eskalationen** die Notifikation erneut zu.

## Laufende Prüfung

Der Workflow `.github/workflows/ci.yml` führt bei jedem Push, bei Pull Requests und jeden Montag
Lint, Tests, die Prüfung der Nachweistabelle, `make audit` und `make sbom` aus und legt die SBOM als
Artefakt ab. **GitHub Actions ist im Repository derzeit abgeschaltet**, die Prüfungen laufen lokal
mit `make lint`, `make test`, `make audit` und `make sbom`. Dependabot schlägt wöchentlich Updates
für Python-Pakete, Docker-Images und Actions vor.

## Sicherheitsrelevante Festlegungen

- **INV-03:** Kein Datensatz wird physisch gelöscht. Die ORM-Methoden werfen einen Fehler, und
  PostgreSQL-Trigger lehnen `DELETE` und `TRUNCATE` ab, auch bei direktem SQL.
- **M-05:** Jede Ansicht muss ihre erlaubten Rollen angeben (`@allow_roles`) oder ausdrücklich
  öffentlich sein (`@public`). Ansichten ohne Angabe werden mit 403 abgelehnt. Eine Anmeldung ohne
  genau eine Rollengruppe in Keycloak wird abgewiesen.
- **M-06:** Das Audit-Log ist per Trigger nur anfügbar, `UPDATE` und `DELETE` scheitern in der
  Datenbank.
- **M-02:** Abhängigkeiten exakt gepinnt (`uv.lock` mit Hashes), Images per Digest, Tailwind-CLI
  per Prüfsumme, htmx und Schriften lokal mit Prüfsumme (`src/static/third_party.json`).
  `make sbom` erzeugt die SBOM (CycloneDX 1.5: Python-Pakete, Front-End-Dateien, Images),
  `make audit` prüft gegen bekannte Schwachstellen.
- **INV-03 / M-06 auch in der Datenbank:** Die Anwendung verbindet sich mit einer eigenen Rolle
  ohne `DELETE`, `TRUNCATE` und DDL; das Audit-Log darf sie nur ergänzen. Sie kann die Trigger
  nicht entfernen. Migrationen laufen getrennt als Eigentümer (Dienst `migrate`).
- **M-05 im HTTP-Layer:** Content-Security-Policy ohne `unsafe-inline`/`unsafe-eval` (htmx ohne
  `eval`), weitere Sicherheits-Header, angemeldete Seiten mit `no-store`, Sitzungen höchstens
  8 Stunden. Hinter einem TLS-Proxy schaltet `DJANGO_HTTPS=true` sichere Cookies, HSTS und
  Umleitung ein; `manage.py check --deploy` läuft dann ohne Befund.
- **M-04:** Eine Einordnung als IT-Risiko und eine Herabstufung unter 20 sind Anträge. Wirksam
  werden sie erst, wenn ein anderer Risk Manager zustimmt (auch als Prüfregel in der Datenbank).
- **M-09:** Eskalationen enthalten nur die Kennung und einen Link, der eine Anmeldung verlangt.
- **M-10:** Risikomelder sehen nur eigene Risiken: in der Liste, auf der Detailseite und in den
  Zahlen des Dashboards. Eine fremde Kennung antwortet genauso wie eine nicht vergebene (404), die
  Antwort verrät also nicht, dass es das Risiko gibt.
- **M-01:** Eingaben erreichen ReportLab nur maskiert; Markup in Titel oder Beschreibung erscheint
  als Text (getestet auch mit der Nutzlast von CVE-2023-33733).
- **M-03:** Das PDF erzeugt der Dienst `pdf-renderer` im Netz `pdf` ohne Route zur Datenbank, ohne
  Zugangsdaten, mit schreibgeschütztem Dateisystem und ohne Capabilities.
- **M-07 / M-08:** Export nur für Risk Manager und nur mit Filter; jede Datei nennt Person und
  Zeitpunkt (CSV je Zeile, PDF auf jeder Seite und in den Metadaten, Dateiname). Jeder Export steht
  im Audit-Log.
- **T-04:** Zellen, die mit `=`, `+`, `-`, `@`, Tab oder Wagenrücklauf beginnen, werden im CSV mit
  einem Apostroph entschärft.
