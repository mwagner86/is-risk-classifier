# IS-Risk Classifier

Leichtgewichtige Web-Anwendung zur Erfassung von Risiken: trennt IT-Risiken und
Informationssicherheitsrisiken (IS-Risiken) anhand von Schutzzielen und Ursprung, berechnet
R = P × I und eskaliert kritische IS-Risiken an das Incident-Response-Team. Spezifiziert im Modul
Softwaretechnik (SS26), Projekt der Hand-ins in Entwicklung sicherer Softwaresysteme (WS26).

## Stand

- **Phase:** Iteration 1 fertig (07.10.2026), noch nicht committet. Nächste: Iteration 2.
  INV-01 gibt es nicht (Max, 07.10.2026) — die Spezifikation kennt nur INV-02 und INV-03.
- **Iterationen (freigegeben 07.10.2026):** 1 Gerüst, Container, Anmeldung, Modelle,
  Zustandsmaschine · 2 Kategorisierung, Risikowert, Eskalation (Benachrichtigung als Mock) ·
  3 Dashboard und Design · 4 Export und Audit-Log · 5 Härtung M-01 bis M-09, SBOM ·
  6 Benachrichtigungsmodul (echter Versand).

## Entscheidungen (07.10.2026)

1. **Stack:** Django + HTMX, PostgreSQL, pytest (pytest-django). `uv` mit Lockfile, SBOM per
   `cyclonedx-py` (M-02). Tailwind als gepinntes Standalone-Binary, kein npm. PDF mit ReportLab
   (aktuelle Version). Asynchrone Benachrichtigung über eine Warteschlange in der Datenbank
   (Notification als Outbox) und einen Worker-Container — kein Celery, kein Redis. Django-Admin
   für Fachmodelle aus (Löschaktionen brechen INV-03).
2. **Anmeldung:** Keycloak im Compose über OIDC, Rollen aus Gruppen, Realm-Export mit einem
   Testkonto je Rolle im Repo. Kein zweiter, lokaler Anmeldeweg. Tests ohne Keycloak.
3. **Ursprung:** Enum mit fünf Werten — „Technisches Versagen / Verschleiß", „Vorsätzlicher
   Angriff", „Menschliches Versehen", „Umwelt / höhere Gewalt", „Unbekannt". Nur
   `TECHNICAL_FAILURE` führt (bei reiner Verfügbarkeit) zum IT-Risiko.
4. **Benachrichtigung — zuerst nur als Mock, das Modul kommt zuletzt (Iteration 6):**
   - Bis dahin eine Schnittstelle `NotificationGateway` mit einer Mock-Implementierung in der App.
     Der Mock verschickt nichts, er hält Nachrichten fest und simuliert den Ausfall per
     `NOTIFY_MOCK_MODE=ok|timeout|5xx` — so sind AK-03.3 und die rote Markierung schon vorher
     testbar und im Browser vorführbar.
   - Outbox und Worker bleiben von Anfang an, weil AK-03.1 asynchronen Versand verlangt; der
     Worker ruft den Mock auf.
   - Weitergabe an IT-Operations über dieselbe Schnittstelle, erst nach Freigabe (M-04). Inhalt
     nach M-09: nur Kennung und Link — schon gegen den Mock getestet.
   - Iteration 6: eigener Stub-Container als HTTP-Gateway, E-Mail weiter an Mailpit, SMS nur
     protokolliert, Ausfall erzwingbar per `NOTIFY_FAILURE_MODE=none|timeout|5xx`. Austausch der
     Implementierung, die Tests aus Iteration 2 laufen unverändert gegen beide.
5. **CMDB:** Asset-Tabelle (Name, Kritikalität 1–5) mit Beispieldaten, Import per
   Management-Command aus CSV, in der App nur lesbar.
6. **Ablauf und Freigabe:**
   - DRAFT: Melder speichert, Pflichtfelder dürfen fehlen. „Einreichen" prüft US-01 und berechnet
     die Kategorie → CATEGORIZED. Berechnet sich IT, bleibt wirksam IS, die IT-Einordnung ist ein
     Antrag (M-04, gilt schon bei der Erfassung).
   - CATEGORIZED: Risk Manager setzt P und I → SCORED. Ist wirksam IS und R ≥ 20 → sofort
     ESCALATED.
   - SCORED: Schutzziele, Ursprung, P, I änderbar (Risk Manager). Hochstufung wirkt sofort,
     Herabstufung (IS → IT, R von ≥ 20 auf < 20) ist ein Antrag. „Bewertung abschließen" →
     VALIDATED nur bei [IT ∨ R < 20] und ohne offene Anträge.
   - Anträge gibt ein Risk Manager frei, der sie nicht selbst gestellt hat.
   - ESCALATED: freigegebene Herabstufung ändert den Wert, der Zustand bleibt bis zur
     dokumentierten Incident Response (CISO oder Risk Manager) → VALIDATED.
   - Ab VALIDATED eingefroren. Änderung über OBSOLETE + neuer DRAFT mit Verweis auf den Vorgänger
     — für CLOSED wie spezifiziert, für VALIDATED als Erweiterung (ersetzt VALIDATED → ESCALATED).
   - Zusätzliche Klassen: ApprovalRequest (Antrag) und AuditEntry (M-06).
7. **Gateway-Ausfall:** dauerhaft rot mit Warnsymbol und Text „Notifikation fehlgeschlagen",
   höchstens kurzer Puls ohne `prefers-reduced-motion` (WCAG 2.2.2). Rot bis eine erneute
   Zustellung gelingt (Schaltfläche für ADMIN); der Audit-Eintrag bleibt. Sichtbar für
   RISK_MANAGER, CISO und ADMIN.

8. **Container (Ergänzung):** Alles läuft als Container, auch App, Worker, Tests und Werkzeuge —
   auf dem Host genügen Docker und `make`. Ein Dockerfile mit mehreren Stufen für `web`, `worker`
   und `pdf-renderer`. Basis-Images per Digest gepinnt, Prozesse ohne root, Healthchecks,
   benannte Volumes für PostgreSQL und Keycloak. Getrennte Netze: `pdf-renderer` (und ab
   Iteration 6 `notify-gateway`) erreichen die Datenbank nicht (M-03). Nur `web` und Keycloak (ab
   Iteration 6 auch Mailpit) sind auf `127.0.0.1` veröffentlicht. Ziel ist der lokale Kontext
   `default`, nicht der Homeserver.

**Weitere Festlegungen aus der Prüfung der Quellen:**

- Reihenfolge nach dem Zustandsdiagramm: erst kategorisieren, dann bewerten.
- Eskalationsempfänger: IR-Team als konfigurierte Empfängergruppe (keine Rolle).
- Mehrere Schutzziele wählbar; C oder I gesetzt → IS.
- P und I: Browser prüft nur als Komfort, Server verwirft; Feld markiert, Meldung nennt die
  Dimension („Zulässiger Wertebereich für das Schadensausmaß ist 1 bis 5"), Score zeigt
  „Nicht berechenbar".
- Risikostufen wie im Threat Model: kritisch ≥ 20, hoch 12–19, mittel 6–11, niedrig 1–5.
- CSV-Export gegen Formelinjektion (T-04, CWE-1236) absichern und testen, obwohl ohne M-Nummer.

## Spezifikation

**Maßgeblich ist [docs/START-PROMPT.md](docs/START-PROMPT.md)** — Rollen, US-01 bis US-04, Invarianten,
Zustandsmaschine, Klassen, M-01 bis M-09, Design. Bei Unklarheiten die Quellen lesen, **nur
lesen, nie ändern**:

| Quelle | Inhalt |
| --- | --- |
| `~/vault/Studium/4. Semester SS26/Softwaretechnik/ESAs/ESA1 - Requirements.md` | US-01 bis US-03, AK-xx.x, Feedback des Dozenten |
| `~/vault/Studium/4. Semester SS26/Softwaretechnik/ESAs/ESA2 - UML v2.md` | Aktivitäts-, Klassen-, Zustandsdiagramm, Feedback |
| `~/Uni/Abgaben/softwaretechnik/esa2/ERKLAERUNG.md`, `regenerate_diagrams.py` | Begründungen, Mermaid-Quellen |
| `~/Uni/ESS/esa/esa1/texs/010-bedrohungsmodell.tex`, `020-detailanalyse.tex` | Architekturannahme, US-04, M-01 bis M-09 |
| `~/Uni/ESS/esa/esa1/THREATMODEL.md` | Datenflüsse F1 bis F13, Vertrauensgrenzen, Kandidaten T-04 bis T-10 |

Bei M-xx gilt der Wortlaut in `020-detailanalyse.tex`; M-04 umfasst dort ausdrücklich auch die
Einordnung als IT-Risiko **schon bei der Erfassung**.

## Leitplanken, die in jeder Iteration gelten

- **INV-02:** Kategorie ist genau `IS_RISIKO` oder `IT_RISIKO`. Komposition über Enum, keine
  Vererbung; Disjunktheit per Validierung, Reklassifizierung zur Laufzeit möglich.
- **INV-03:** Nichts wird physisch gelöscht, auch nicht über Admin, ORM-Kaskaden oder Migrationen.
  Statt Löschen → `OBSOLETE`. Audit-Log nur anfügen (M-06).
- **Zustandsmaschine** an genau einer Stelle implementieren; jeder nicht erlaubte Übergang wird
  abgelehnt. `ESCALATED → OBSOLETE` und `CLOSED → DRAFT` sind verboten.
- **IT-Risiken eskalieren nie**, auch nicht bei R ≥ 20.
- **Deny by default (M-05):** Rechte serverseitig je Rolle prüfen; Validierung (z. B. P und I)
  immer auch serverseitig.
- **Meldungen aus der Spezifikation wörtlich übernehmen.** Bei AK-02.2 nennt die Meldung nach dem
  Feedback des Dozenten die Dimension.

## Arbeitsweise

- **Tests zuerst.** Je Abnahmekriterium ein Test, benannt nach seiner Kennung (`test_ak_01_1_…`),
  je Gegenmaßnahme mindestens einer (`test_m_04_…`). Zustandsmaschine vollständig, inklusive aller
  verbotenen Übergänge.
- **Sprache:** Code, Bezeichner, Kommentare, Commit-Nachrichten, Branch- und Dateinamen englisch.
  Oberfläche und Meldungen deutsch. Gespräch und diese Datei deutsch.
- **Makefile** mit `make dev`, `make test`, `make lint`; ruff, Typannotationen; Abhängigkeiten
  gepinnt; `.env.example` statt Geheimnissen; README mit Start in drei Befehlen.
- **Docker:** Kontext `default` auf der Workstation. **Nicht** auf dem Homeserver
  (Kontext `homeserver`) starten.
- **Git:** Commits und Pushes nur auf Anweisung. Remote (geplant): privat,
  `mwagner86/is-risk-classifier`, noch nicht angelegt.
- **Systemänderungen** (Pakete, Docker-Volumes, Ports, Konfiguration außerhalb des Repos) in
  `~/CHANGELOG.md` protokollieren — mit Befehl, Verifikation und Rückbau.
- **Hand-ins in `~/Uni/ESS` bleiben unberührt.** Ob und wie die Implementierung dort vorkommt,
  entscheidet Max.

## Design

Stil nach dependencytrack.org, **ohne** Logo und Markennamen von OWASP oder Dependency-Track.
Tokens, Schriften und Seitenaufbau stehen in docs/START-PROMPT.md, Abschnitt „Design". Kontraste nach
WCAG AA prüfen; Animationen nur ohne `prefers-reduced-motion`.

## Technik

Aufbau, Befehle und Demo-Konten: [README.md](README.md). Für Agenten zusätzlich:

- **Verzeichnisse:** Code unter `src/` (`config/`, `apps/<app>/`, `templates/`), Tests unter
  `tests/`, Container-Dateien unter `docker/`, Spezifikation unter `docs/`. Im Wurzelverzeichnis
  nur Projektdateien (Makefile, compose.yaml, pyproject.toml, uv.lock, README, CLAUDE.md,
  `.env.example`, Dotfiles). Apps heißen im Import `apps.<app>`, ihr Label bleibt `<app>`
  (Tabellen, Migrationen, `"risks.Risk"`).

- **Alles im Container.** `make test`, `make lint`, `make migrations` laufen über die
  Compose-Dienste `test` (mit DB) und `tools` (ohne DB), Profil `tools`. Kein lokales venv.
- **Abhängigkeiten:** in `pyproject.toml` exakt pinnen (`==`), dann `make lock`. Django bleibt auf
  der LTS-Linie 5.2; `django-stubs` muss zur Django-Version passen (5.2.x), nicht zur neuesten.
- **Images** per Tag und Digest pinnen (Dockerfile-`ARG`s, `compose.yaml`).
- **Neue Ansicht:** immer `@allow_roles(...)` oder `@public`; der Test
  `test_m_05_every_route_declares_its_access` schlägt sonst fehl. Neue öffentliche Routen in
  `PUBLIC_ROUTES` (tests/test_access.py) eintragen — bewusst, nicht nebenbei.
- **Neues Fachmodell:** von `apps.core.models.BaseModel` erben, Fremdschlüssel mit `on_delete=PROTECT`,
  und in einer Migration `apps.core.db.forbid_delete("<tabelle>")` anlegen (Muster:
  `src/apps/*/migrations/0002_database_guards.py`); dann in `PROTECTED_MODELS` (tests/test_invariants.py)
  aufnehmen.
- **Statuswechsel** nur über `apps.risks.state_machine.transition()`; nie `risk.status = …` direkt.
- **Enum-Werte** (`NUTZER`, `IS_RISIKO`, …) folgen den Literalen des UML-Modells; Bezeichner sonst
  englisch. Rollen = Keycloak-Gruppennamen.
- **Tests** markieren: `@pytest.mark.req("AK-01.1")`, `"M-05"`, `"INV-03"`, `"SM"`
  (Zustandsmaschine). Name beginnt mit der Kennung (`test_ak_01_1_…`, `test_m_05_…`).
- **Fallstricke:**
  - Fremdschlüssel sind in PostgreSQL `DEFERRABLE`. Ein `TRUNCATE` im Test scheitert dann an
    „pending trigger events" statt am eigenen Trigger — vorher `SET CONSTRAINTS ALL IMMEDIATE`.
  - Keycloak-Volume liegt auf `/opt/keycloak/data` (gehört im Image dem Keycloak-Benutzer); auf
    `/opt/keycloak/data/h2` gehört es root und Keycloak startet nicht.
  - Keycloak liest `${VAR}`-Platzhalter im Realm-Export aus der Umgebung (Client-Secret,
    Demo-Passwort). Änderungen am Realm wirken erst nach `make reset`.
  - Pythons `http.cookiejar` schickt Cookies für `localhost` nicht zurück; für
    End-to-End-Proben des Logins curl nehmen.
- **Noch nicht vorhanden** (laut Plan später): Worker und Outbox (2), Tailwind und Design (3),
  `pdf-renderer` (4), Laufzeit-Image mit gunicorn, CSP, getrennte DB-Rollen für Migration und
  Betrieb (5), `notify-gateway` und Mailpit (6).
