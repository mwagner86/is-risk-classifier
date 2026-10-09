# Belege zu den Kandidaten T-04 bis T-10

Grundlage für die Bewertung in der Threat-Dragon-Sitzung (ESS, Hand-in 1). Die Kandidaten stehen
in `esa/esa1/THREATMODEL.md` im ESS-Repo. Diese Tabelle hält fest, was die Implementierung
dagegen tut und welcher Test das belegt. **Die Bewertung von P und I bleibt Teil der Analyse**, sie
steht hier bewusst nicht. Stand 09.10.2026, Commit nach `00b9ae3`.

| Kandidat | STRIDE | Was der Code dagegen tut | Beleg (Test) | Was offen bleibt |
| --- | --- | --- | --- | --- |
| **T-04** Formelinjektion in der CSV-Exportdatei | T | Zellen, die mit `=`, `+`, `-`, `@`, Tab oder Wagenrücklauf beginnen, werden entschärft (CWE-1236). Export nur für Risk Manager und nur gefiltert (M-07) | `test_t_04_formula_injection_is_neutralised`, `test_m_07_every_export_is_audited` | Die Datei verlässt das System. Was ein Empfänger damit tut, liegt außerhalb |
| **T-05** Gefälschte Eskalationsnachricht an das IR-Team | S | Nachrichten enthalten nur Kennung und Link, der Link führt erst zur Anmeldung (M-09). Senden kann nur der Worker: Das Gateway verlangt ein Token und hängt in einem internen Netz | `test_m_09_escalation_contains_only_identifier_and_link`, `test_m_09_link_leads_to_login_first`, `test_gateway_requires_the_token` | Eine von außen gefälschte Mail an die IR-Adressen verhindert die App nicht. Signatur und Absenderprüfung (DKIM, SPF) liegen beim Mailsystem, im Stack ist das Mailpit |
| **T-06** Ausfall des Benachrichtigungsdienstes | D | Die Outbox in der Datenbank verliert nichts. Ein Fehlschlag wird ins Audit-Log geschrieben und bleibt rot markiert, bis eine erneute Zustellung gelingt. Erneut senden kann die Administration (AK-03.3, Entscheidung 7) | `test_ak_03_3_gateway_failure_is_logged_and_flagged`, `test_ak_03_3_failed_risk_is_highlighted_on_the_dashboard`, `test_admin_resends_from_the_escalation_page` | Kein automatischer zweiter Versuch, keine Ersatzzustellung über einen anderen Kanal |
| **T-07** Übernommenes Konto eines Risk Managers | S | Keycloak sperrt nach Fehlversuchen (`bruteForceProtected`). Sitzungen laufen nach 8 h ab, Cookies sind `HttpOnly` und `SameSite=Lax`. Eine Herabstufung braucht einen zweiten Risk Manager (M-04). Jede Änderung steht mit Urheber im Audit-Log (M-06) | `test_m_05_sessions_expire`, `test_m_04_requester_cannot_approve_own_request`, `test_m_06_entry_records_author_time_old_and_new_value` | **Keine MFA, keine Passwortrichtlinie** im Realm. Mit einem Konto lässt sich hochstufen, exportieren und eigene Anträge stellen. Abschwächen geht nur zu zweit |
| **T-08** Änderungen ohne eindeutigen Urheber | R | Das Audit-Log hält bei jeder Änderung an Schutzzielen, Ursprung, P und I Urheber, Zeitpunkt, alten und neuen Wert fest. Jeder Statuswechsel wird geloggt. Rollen kommen bei jedem Login frisch aus Keycloak (M-06, M-05) | `test_m_06_changes_to_goals_origin_p_and_i_are_audited`, `test_m_06_every_transition_is_audited`, `test_m_05_role_follows_the_identity_provider_on_every_login` | Urheber ist das Konto, nicht die Person. Ein geteiltes oder übernommenes Konto (T-07) schlägt durch |
| **T-09** Direkter Lesezugriff auf die Datenbank | I | PostgreSQL ist nicht veröffentlicht und hängt in einem internen Netz ohne Route nach außen. PDF-Renderer und Gateway erreichen die Datenbank nicht (M-03). Die App verbindet sich mit einer eingeschränkten Rolle. Zugangsdaten sind je Installation zufällig | `test_app_role_is_not_privileged`, `test_app_role_may_delete_only_where_the_application_must` | Die App-Rolle darf alles **lesen**. Die Daten liegen unverschlüsselt im Volume, und innerhalb des Docker-Netzes gibt es kein TLS |
| **T-10** Manipulation des Audit-Logs | T | Das Audit-Log ist append-only: Die App-Rolle hat kein `UPDATE` und kein `DELETE` darauf, und auch das Modell verweigert Änderungen (M-06, INV-03) | `test_m_06_app_role_can_only_append_to_the_audit_log`, `test_inv_03_database_refuses_raw_delete`, `test_inv_03_app_role_cannot_delete_or_truncate` | Wer die Zugangsdaten des Datenbank-Eigentümers hat (`.env`, `migrate`, `test`), kann ändern. Keine Hash-Kette, kein Export in ein externes Log |

## Lesende Zugriffe auf das Register — für das Datenflussdiagramm

Aus [`access-matrix.md`](access-matrix.md). Im Diagramm der ESA 1 führen die Flüsse nur zum Register
hin (F1, F3) und vom Register in Export (F10, F11) und Eskalation (F7). Die **Anzeige im Browser**
fehlt:

| Ansicht | Rollen | Inhalt |
| --- | --- | --- |
| `risk_list`, `risk_detail`, `dashboard` | alle vier, `NUTZER` nur eigene Risiken | Titel, Beschreibung, Schutzziele, Ursprung, Assets, P, I, Status |
| `audit_log` | Risk Manager, CISO, Administration | alte und neue Werte aller Änderungen, also ebenfalls Registerinhalt |
| `escalation_list` | Risk Manager, CISO, Administration | eskalierte Risiken, fehlgeschlagene Zustellungen |
| `asset_list` | alle vier | CMDB-Spiegel (Name, Kritikalität), nur lesend |

**Beobachtung, keine Änderung:** Die Administration (`ADMIN`) sieht das ganze Register samt
Beschreibungen und Assets. Ihre Aufgaben laut Spezifikation sind das erneute Senden und die rote
Markierung (US-03, AK-03.3). Gemessen an need-to-know ist das mehr als nötig. Das betrifft T-03 und
die vorläufige M-10 in Hand-in 2.
