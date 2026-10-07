# Start-Prompt: IS-Risk Classifier bauen

Stand: 07.10.2026, geschrieben auf der Workstation. Zum Einfügen in einen neuen Chat, gestartet in
`~/Uni/IS-Risk-Classifier/` (WSL). Der Ordner enthält bisher nur diese Datei. Alles Fachliche ist
unten zusammengefasst; die Quellen sind für Rückfragen angegeben.

---

```text
Ich möchte den IS-Risk Classifier bauen: ein leichtgewichtiges Werkzeug zur Erfassung von Risiken,
das IT-Risiken und Informationssicherheitsrisiken (IS-Risiken) automatisch trennt, einen Risikowert
berechnet und kritische IS-Risiken eskaliert. Spezifiziert habe ich ihn im Modul Softwaretechnik
(SS26), im Modul Entwicklung sicherer Softwaresysteme (WS26) ist er das Projekt meiner Hand-ins.
Ziel dieses Chats: eine lauffähige, getestete Web-Anwendung, Schritt für Schritt. Das Design
orientiert sich an https://dependencytrack.org/.

## Quellen (lesen, wenn unten etwas unklar ist)

- Anforderungen: ~/vault/Studium/4. Semester SS26/Softwaretechnik/ESAs/ESA1 - Requirements.md
  (US-01 bis US-03 mit Abnahmekriterien, darunter die Rückmeldungen des Dozenten)
- Modell: ~/vault/Studium/4. Semester SS26/Softwaretechnik/ESAs/ESA2 - UML v2.md und
  ~/Uni/Abgaben/softwaretechnik/esa2/ERKLAERUNG.md (Klassen, Zustände, Invarianten);
  Mermaid-Quellen in ~/Uni/Abgaben/softwaretechnik/esa2/regenerate_diagrams.py
- Architekturannahme, US-04, Bedrohungen: ~/Uni/ESS/esa/esa1/texs/010-bedrohungsmodell.tex,
  020-detailanalyse.tex (Gegenmaßnahmen M-01 bis M-09), ~/Uni/ESS/esa/esa1/THREATMODEL.md
  (Datenflüsse F1 bis F13, Vertrauensgrenzen)
- Diese Quellen nur lesen, nicht ändern.

## Fachliche Spezifikation

Rollen (Enum Role): NUTZER (Risikomelder aus den Fachbereichen), RISK_MANAGER, CISO, ADMIN. Das
Incident-Response-Team ist eine Empfängergruppe für Eskalationen.

US-01 Kategorisierung (Risikomelder erfasst):
- Pflichtangaben: Titel, Beschreibung, betroffene Schutzziele (Vertraulichkeit, Integrität,
  Verfügbarkeit, mehrere möglich), Ursprung.
- Vertraulichkeit oder Integrität betroffen -> IS-Risiko, Pflichtfeld "Betroffene Assets" wird frei.
- Nur Verfügbarkeit UND Ursprung "Technisches Versagen / Verschleiß" -> Allgemeines IT-Risiko,
  Weitergabe an IT-Operations-Management.
- Nur Verfügbarkeit mit anderem Ursprung -> IS-Risiko.
- Kein Schutzziel -> Speichern blockiert. Ursprung leer -> Speichern blockiert, Feld fokussiert,
  Meldung "Ursprung muss zur CIA-Klassifizierung zwingend angegeben werden".
US-02 Risikowert (Risk Manager bewertet):
- Eintrittswahrscheinlichkeit P und Schadensausmaß I, je ganzzahlig 1 bis 5, R = P x I.
- Außerhalb 1 bis 5 oder keine Zahl -> verwerfen, Feld markieren, Meldung mit Dimension, z. B.
  "Zulässiger Wertebereich für das Schadensausmaß ist 1 bis 5". Prüfung immer auch serverseitig.
US-03 Eskalation:
- IS-Risiko UND R >= 20 -> Status ESCALATED, asynchrone Benachrichtigung (E-Mail/SMS) an das
  Incident-Response-Team. Ein IT-Risiko eskaliert nie, auch bei R >= 20.
- Fällt das Gateway aus (Timeout, HTTP 5xx): Audit-Log-Eintrag "Notifikation fehlgeschlagen", das
  Risiko bleibt im Dashboard für alle Administratoren dauerhaft rot hervorgehoben.
US-04 Export (Risk Manager): Risiken gefiltert als CSV und als PDF. Nach dem Feedback des Dozenten
als zwei getrennte Anforderungen umsetzen, nicht als eine.

Invarianten:
- INV-02: Kategorie ist genau IS_RISIKO oder IT_RISIKO, nie beides, keine dritte. Reklassifizierung
  zur Laufzeit möglich (Komposition über Enum, keine Vererbung) -> Disjunktheit per Validierung.
- INV-03: Nichts wird physisch gelöscht. Statt Löschen -> Status OBSOLETE.

Zustandsmaschine (Enum RiskStatus):
DRAFT -> CATEGORIZED (US-01) -> SCORED (US-02) -> ESCALATED [IS und R >= 20] oder VALIDATED
[IT oder R < 20]; ESCALATED -> VALIDATED nur mit dokumentierter Incident Response; VALIDATED ->
CLOSED. OBSOLETE aus DRAFT, CATEGORIZED, SCORED, VALIDATED und CLOSED, nicht aus ESCALATED.
CLOSED -> OBSOLETE (Re-Evaluierung) legt einen neuen DRAFT an; CLOSED -> DRAFT direkt ist verboten.
Alle anderen Übergänge ablehnen.

Klassen: User, Risk (Titel, Beschreibung, Status, erstellt am), RiskAssessment (P, I, Score,
Ursprung, Kategorie), CIATriade (drei boolesche Schutzziele), Asset (aus der CMDB, Name,
Kritikalität; existiert unabhängig, n:m zu Bewertungen), Notification (Zeitpunkt, zugestellt ja/nein).
Feedback des Dozenten beachten: IDs nicht je Klasse benennen (gemeinsame Basis), Kategorie nicht
doppelt als Attribut und Beziehung modellieren, keine Abläufe als Assoziationen.

## Sicherheitsanforderungen (aus meinem Threat Model, ESS Hand-in 1)

- M-01: Nutzereingaben vor der PDF-Erzeugung als Text maskieren, kein Markup aus Eingaben
- M-02: Drittkomponenten inventarisieren und laufend gegen bekannte Schwachstellen prüfen
  (Abhängigkeiten pinnen, SBOM im CycloneDX-Format erzeugbar machen)
- M-03: PDF-Erzeugung in einem eigenen Prozess ohne Datenbankzugang
- M-04: Eine Einordnung als IT-Risiko und eine Herabstufung eines IS-Risikos unter 20 werden erst
  wirksam, wenn ein anderer Risk Manager sie freigibt; bis dahin gilt die strengere Einstufung
- M-05: Rechte serverseitig je Rolle prüfen, alles nicht Erlaubte ablehnen (deny by default)
- M-06: Jede Änderung an Schutzzielen, Ursprung, P und I mit Urheber, Zeitpunkt, altem und neuem
  Wert in ein Audit-Log, an das nur angefügt werden kann
- M-07: Export nur für Risk Manager und nur gefiltert, jeder Export im Audit-Log
- M-08: Jede Exportdatei mit exportierender Person und Zeitpunkt kennzeichnen
- M-09: Eskalationen enthalten nur Kennung und Link, der erst nach Anmeldung zum Risiko führt
Jede Gegenmaßnahme bekommt mindestens einen automatisierten Test.

## Entscheidungen, die du zuerst mit mir klärst

Für jede eine Empfehlung mit Begründung vorlegen, dann meine Antwort abwarten:
1. Stack. Vorschlag: Python mit Django (ORM, Migrationen, CSRF, Sessions und Rollen von Haus aus),
   Server-Templates mit HTMX, Tailwind für die Design-Tokens; PostgreSQL; pytest.
2. Anmeldung. Der Firmen-IdP aus der Annahme existiert nicht. Vorschlag: Keycloak im Docker
   Compose mit OIDC, Rollen aus Gruppen; Alternative: lokale Konten.
3. Werte für "Ursprung". Die Spezifikation nennt nur "Technisches Versagen / Verschleiß". Vorschlag:
   zusätzlich "Vorsätzlicher Angriff", "Menschliches Versehen", "Umwelt / höhere Gewalt",
   "Unbekannt".
4. Benachrichtigung. Vorschlag: E-Mail über Mailpit im Compose, SMS als Stub, dessen Ausfall sich
   per Einstellung erzwingen lässt (zum Testen der Gateway-Ausfall-Regel aus US-03).
5. CMDB. Vorschlag: Asset-Tabelle mit Beispieldaten und CSV-Import, in der App nur lesbar.
6. Ablauf zwischen Erfassen und Bewerten: Wer setzt P und I wann, wie läuft die Freigabe nach
   M-04 durch die Zustände? Vorschlag als kleines Zustandsbild zeigen.
7. Darstellung der Gateway-Ausfall-Regel: "rot blinkend" aus der Spezifikation widerspricht der
   Barrierefreiheit. Vorschlag: dauerhaft rot mit Symbol, Animation nur ohne prefers-reduced-motion.

## Design nach dependencytrack.org

Nur den Stil übernehmen, kein Logo und keine Markennamen von OWASP oder Dependency-Track.
- Dunkles Thema als Standard. Hintergrund #08061a / #0c0823, Flächen #161d2c / #1a2233 / #212a40,
  Ränder #262f47 / #28324c, Karten mit etwa 9 px Eckenradius.
- Text #e6ebf5, gedämpft #8190ac und #69748f. Markenverlauf für Akzente: #ff00cf -> #a855ff ->
  #7cc4ff -> #6c8cff -> #3df0d0.
- Signalfarben: kritisch #ff4d6a, Warnung #f5a623, Info #34d2f5.
- Schriften: Plus Jakarta Sans für Überschriften, Inter für Text, eine Monospace für Kennungen.
- Aufbau wie die Dependency-Track-Oberfläche: Seitenleiste mit Navigation (Dashboard, Risiken,
  Assets, Eskalationen, Audit-Log, Export, Verwaltung), oben Breadcrumb und Nutzer.
- Dashboard: Kennzahlkarten (offene Risiken, IS gegenüber IT, eskaliert, Notifikation
  fehlgeschlagen), Risikomatrix 5 x 5 als Heatmap, Tabellen mit farbigen Badges je Risikostufe.
  Stufen als Vorschlag: R >= 20 kritisch, 10 bis 19 hoch, 5 bis 9 mittel, 1 bis 4 niedrig.
- Kontraste nach WCAG AA prüfen.

## Arbeitsweise

- Erst die Entscheidungen klären, dann einen Plan in Iterationen vorlegen und meine Freigabe
  abwarten. Vorschlag: 1 Gerüst, Compose, Anmeldung, Modelle, Zustandsmaschine; 2 Kategorisierung,
  Risikowert, Eskalation; 3 Dashboard und Design; 4 Export und Audit-Log; 5 Härtung M-01 bis M-09,
  SBOM.
- Tests zuerst, abgeleitet aus den Abnahmekriterien: je Kriterium ein Test, benannt nach seiner
  Kennung (AK-01.1 ...), dazu je Gegenmaßnahme M-xx. Die Zustandsmaschine vollständig testen,
  auch die verbotenen Übergänge.
- Makefile mit make dev, make test, make lint; ruff, Typannotationen; README mit Start in drei
  Befehlen; .env.example statt Geheimnissen im Repository; Abhängigkeiten gepinnt.
- Läuft lokal mit Docker (Kontext default auf der Workstation), nicht auf dem Homeserver.
- Code, Bezeichner, Kommentare und Commit-Nachrichten englisch; Oberfläche und Meldungen deutsch,
  Meldungen aus der Spezifikation wörtlich.
- Git-Repository hier anlegen. Ein GitHub-Repository (privat, mwagner86/is-risk-classifier), Commits
  und Pushes nur, wenn ich es sage. Systemänderungen in ~/CHANGELOG.md protokollieren.
- Die Hand-ins in ~/Uni/ESS bleiben unberührt: ESA 1 analysiert bewusst die Spezifikation. Ob und
  wie die Implementierung dort vorkommt, entscheide ich.

Erster Schritt: die Spezifikation oben in zwei, drei Sätzen zurückspiegeln, Widersprüche nennen,
dann die sieben Entscheidungen mit Empfehlungen vorlegen.
```
