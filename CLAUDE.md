# IS-Risk Classifier

Leichtgewichtige Web-Anwendung zur Erfassung von Risiken: trennt IT-Risiken und
Informationssicherheitsrisiken (IS-Risiken) anhand von Schutzzielen und Ursprung, berechnet
R = P × I und eskaliert kritische IS-Risiken an das Incident-Response-Team. Spezifiziert im Modul
Softwaretechnik (SS26), Projekt der Hand-ins in Entwicklung sicherer Softwaresysteme (WS26).

## Stand

- **Phase:** Iterationen 1 (`c487c30`), 2 (`ea7cbe0`), 3 (`55cbd40`), 4 (`445bb3a`),
  5 (`a501040`) und 6 (`b16d76e`) committet (07.10.2026). Der freigegebene Plan ist abgearbeitet.
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
- **Git:** Commits und Pushes nur auf Anweisung. Remote `origin`:
  `git@github.com:mwagner86/is-risk-classifier.git` (privat, angelegt am 07.10.2026).
- **Systemänderungen** (Pakete, Docker-Volumes, Ports, Konfiguration außerhalb des Repos) in
  `~/CHANGELOG.md` protokollieren — mit Befehl, Verifikation und Rückbau.
- **Hand-ins in `~/Uni/ESS` bleiben unberührt.** Ob und wie die Implementierung dort vorkommt,
  entscheidet Max.

## Design

Umgesetzt in Iteration 3: Tokens in `src/assets/app.css` (`@theme`, Tailwind-Quelle, wird nicht ausgeliefert), gebaut vom Tailwind-
Standalone-CLI im Compose-Dienst `css` (Watch) bzw. `make css`. Ausgabe
`src/static/css/build/app.css` ist ignoriert. Schriften und htmx lokal, Inventar
`src/static/THIRD_PARTY.md`. Abweichungen von der Vorgabe wegen WCAG AA: `#69748f` nur für Deko und
große Schrift, `#8190ac` nicht auf `#212a40`; Badges vollfarbig mit dunkler Schrift; zusätzlicher
Token `level-medium #e8d44d`, `danger-strong #ff8095` für Text auf dem roten Grund. Kontraste prüft
`tests/test_ui.py` — neue Farbpaare dort eintragen. Screenshots: `docs/screenshots/`.


Stil nach dependencytrack.org, **ohne** Logo und Markennamen von OWASP oder Dependency-Track.
Tokens, Schriften und Seitenaufbau stehen in docs/START-PROMPT.md, Abschnitt „Design". Kontraste nach
WCAG AA prüfen; Animationen nur ohne `prefers-reduced-motion`.

## Technik

Aufbau, Befehle und Demo-Konten: [README.md](README.md). Für Agenten zusätzlich:

- **Dienste:** `migrate` (einmalig, Eigentümer), `web`, `worker`, `css` (nur dev), `db`,
  `keycloak`, `pdf-renderer` (M-03), `notify-gateway`, `mailpit`; dazu `test` und `tools` (Profil
  `tools`). Netze: `frontend`, `backend` (DB, internal), `pdf` (internal), `notify` (internal).

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
- **Fachlogik** nur in `apps/risks/services.py` (Erfassen, Klassifizieren, Bewerten, Freigeben,
  Incident Response). Views rufen Services auf; Services prüfen Rolle (M-05), validieren
  serverseitig und schreiben Änderungen an Schutzzielen, Ursprung, P, I ins Audit-Log (`_apply`).
- **Kategorie:** die Regel steht allein in `apps/risks/classification.py` (`categorize`). Gespeichert
  wird die *wirksame* Kategorie; eine berechnete IT-Einordnung bleibt bis zur Freigabe IS
  (ApprovalRequest). Assets sind Pflicht, wenn die *berechnete* Kategorie IS ist.
- **Benachrichtigungen:** Outbox in `notifications_notification`, Worker
  `python src/manage.py run_outbox`. Im Stack setzt Compose für den Worker
  `NOTIFICATION_GATEWAY=…HttpGateway` (Dienst `notify-gateway`, Token `NOTIFY_GATEWAY_TOKEN`,
  Ausfall per `NOTIFY_FAILURE_MODE=timeout|5xx` in `.env` + `docker compose up -d notify-gateway`).
  Settings-Standard und Tests: `MockGateway` (`NOTIFY_MOCK_MODE`). Tests mit der Fixture
  `gateway` laufen gegen beide; der HTTP-Fall startet den Gateway-Server im Testprozess. Inhalt nach
  M-09: Kennung und Link. `src/notify_gateway/` wie der PDF-Renderer: nie Django importieren.
- **Export (Iteration 4):** US-04 ist geteilt in **US-04a CSV** und **US-04b PDF** — Kennungen
  vorläufig, bis Max sie im ESS-Hand-in 2 festlegt (nur Testmarker, leicht umzubenennen). Filter
  in `apps/risks/filters.py` (`RiskFilter`), gemeinsam für Liste und Export; ein leerer Filter
  verweigert den Export (M-07). Jeder Export legt ein `Export` an und einen Audit-Eintrag.
- **PDF-Renderer** (`src/pdf_renderer/`): nur Standardbibliothek und ReportLab, **nie** Django oder
  `apps.*` importieren — `tests/test_pdf_renderer.py` prüft das und die Compose-Härtung. Jeder
  Nutzertext geht durch `render.text()` (XML-Escape) in einen `Paragraph`; Kopf- und Fußzeile mit
  `drawString` (kein Markup). Tests rendern in-process (Fixture `inprocess_renderer`).
- **Datenbankrollen (Iteration 5):** `web` und `worker` verbinden sich als `POSTGRES_APP_USER`
  (eingeschränkt, `manage.py setup_db_roles`), `migrate` und `test` als Eigentümer. Neue Tabelle,
  aus der die Anwendung löschen muss: in `DELETE_ALLOWED` der Rolle eintragen — sonst nie.
- **Header/CSP:** `apps/core/security.py`, Policy in den Settings. Kein Inline-Script, kein
  `style=`, kein `on…=`, kein `hx-on` in Templates (Test). Neue externe Ziele für Formulare
  (z. B. ein weiterer IdP) in `form-action` eintragen.
- **Laufzeit-Image:** Stage `runtime` im Dockerfile, gestartet über `compose.prod.yaml`
  (`make prod`). WhiteNoise nur dort (`STATIC_MANIFEST=true`). Die Tailwind-Quelle liegt unter
  `src/assets/`, **nicht** unter `static/`, sonst scheitert `collectstatic` am `@import`.
- **Lieferkette:** neue ausgelieferte Front-End-Datei in `src/static/third_party.json` (mit
  SHA-256) und `THIRD_PARTY.md` eintragen; der Test vergleicht Inventar und Dateien.
- **Sprachen (DE/EN):** Deutsch ist Quellsprache und Standard (`LANGUAGE_CODE = "de"`), die
  deutschen Texte sind die msgids. Jeden neuen Oberflächentext markieren: Templates
  `{% translate %}`/`{% blocktranslate %}`, Python auf Modul-/Klassenebene `gettext_lazy as _`, in
  Funktionen `gettext`. Danach die englische Fassung in `tools/translations_en.py` eintragen und
  `make messages` laufen lassen (`.po` und `.mo` werden versioniert). CI (`make messages-check`)
  scheitert an unübersetzten Texten; `tests/test_i18n.py` findet deutsche Reste auf englischen
  Seiten. Typ für übersetzbare Texte: `StrOrPromise` aus `django_stubs_ext`, nur unter
  `TYPE_CHECKING` importieren (im Laufzeit-Image nicht vorhanden). Der PDF-Renderer hat eigene
  Labels (`LABELS` in `render.py`), die Mails an das IR-Team bleiben deutsch.
- **Formulare:** „Speichern" prüft US-01 vollständig (AK-01.3 wörtlich), „Als Entwurf ablegen"
  speichert ohne Prüfung. Fehlerfelder fokussiert `apps.core.forms.focus_first_error`.
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
  - OIDC-Abgleich darf `set_unusable_password()` nur einmal aufrufen: ein neuer Hash bei jedem
    Login ändert den Session-Hash und meldet das Konto überall sonst ab (Test vorhanden).
  - Pythons `http.cookiejar` schickt Cookies für `localhost` nicht zurück; für
    End-to-End-Proben des Logins curl nehmen.
  - `manage.py shell -c` schreibt in Django 5.2 „N objects imported automatically" auf stdout;
    für maschinenlesbare Ausgabe `shell --no-imports -c` nehmen.
  - **htmx:** Trigger nie mit `change from:#id_…` an Elemente binden, die ausgetauscht werden —
    nach dem ersten Swap hört niemand mehr zu. Den Trigger an den Container hängen, der selbst
    ausgetauscht wird (`#classification`).
  - **htmx:** Ein `<form>` als auslösendes Element wird vor der Anfrage per HTML-Validierung
    geprüft; ungültige Werte (z. B. Impact 6) lösen dann gar keine Anfrage aus. Live-Vorschauen an
    einen Container im Formular hängen (`hx-include="closest form"`).
  - Container mit eingebundenem Quellcode laufen als Eigentümer des Arbeitsverzeichnisses
    (`APP_UID`/`APP_GID` aus dem Makefile). Mit fester UID 1000 scheiterte die CI: Der Checkout
    gehört dort UID 1001, ruff und das SBOM-Skript durften nicht schreiben.
  - `pkill -f`/`pgrep -f` mit einem Muster, das in der eigenen Befehlszeile steht, beendet die
    eigene Shell (Exit 144) — Prozesse über die PID beenden.
  - `select_for_update()` mit `select_related` auf eine umgekehrte 1:1-Beziehung scheitert in
    PostgreSQL („nullable side of an outer join") → `select_for_update(of=("self",))`.
- **CI:** `.github/workflows/ci.yml` — Lint, Tests, Nachweistabelle aktuell (`make trace` +
  `git diff`), `make audit`, `make sbom` als Artefakt; bei Push, PR und montags 05:17 UTC. Actions
  per Commit-Hash gepinnt. Dependabot (`.github/dependabot.yml`) wöchentlich; Django bleibt auf
  5.2 LTS. Nach neuen Tests `make trace` laufen lassen und die Tabelle mitcommitten.
- **Noch nicht vorhanden:** Kein TLS im lokalen Stack (nur `DJANGO_HTTPS` für den Betrieb hinter einem
  Proxy).
