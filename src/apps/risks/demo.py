"""Demo data for development (``manage.py seed_demo``, run by ``make dev``).

A register of 13 risks that covers every state, both categories, open and decided approvals
(M-04), delivered and failed notifications (AK-03.3) and a superseded risk with its successor.
The reporter ``melder`` owns four of them, so the restricted view of a reporter shows at once.

Everything goes through the services and the state machine: the audit log, the outbox and the
approvals are what the application itself writes. Timestamps are the time of the run — the
audit log is append-only, back-dating the risks would contradict it.
"""

from collections.abc import Mapping

from django.db import transaction

from apps.accounts.models import User
from apps.cmdb.models import Asset
from apps.notifications.gateway import GatewayTimeoutError, OutgoingMessage
from apps.notifications.services import process_outbox
from apps.risks import services
from apps.risks.models import (
    ApprovalKind,
    ApprovalRequest,
    ApprovalState,
    Origin,
    Risk,
    RiskStatus,
)
from apps.risks.state_machine import transition

DEMO_USERNAMES = ("melder", "rm.mueller", "rm.schmidt", "ciso")


class _Unreachable:
    """Gateway for one escalation only, so the demo shows a failed delivery (AK-03.3)."""

    def send(self, message: OutgoingMessage) -> None:
        raise GatewayTimeoutError


def _assets(*keys: str) -> list[Asset]:
    assets = list(Asset.objects.filter(cmdb_key__in=keys))
    missing = set(keys) - {asset.cmdb_key for asset in assets}
    if missing:
        raise LookupError(f"CMDB sample data missing: {', '.join(sorted(missing))}")
    return assets


def _capture(
    reporter: User,
    title: str,
    description: str,
    *,
    goals: str,
    origin: Origin,
    assets: tuple[str, ...] = (),
) -> Risk:
    return services.capture(
        reporter,
        title=title,
        description=description,
        confidentiality="C" in goals,
        integrity="I" in goals,
        availability="A" in goals,
        origin=origin,
        assets=_assets(*assets),
    )


def _pending(risk: Risk, kind: ApprovalKind) -> ApprovalRequest:
    request: ApprovalRequest = risk.approval_requests.get(kind=kind, state=ApprovalState.PENDING)
    return request


@transaction.atomic
def _build(users: Mapping[str, User]) -> None:
    melder, mueller, schmidt, ciso = (users[name] for name in DEMO_USERNAMES)

    # --- reported by melder: what a reporter sees ------------------------------------------
    services.save_draft(
        melder,
        title="Unverschlüsselte USB-Sticks im Labor",
        description=(
            "Im Labor werden Messdaten auf private USB-Sticks kopiert, die nicht verschlüsselt "
            "sind. Ursprung und betroffene Systeme kläre ich noch."
        ),
        confidentiality=True,
        assets=_assets("CI-0012"),
    )
    _capture(
        melder,
        "Phishing-Mails mit gefälschten Rechnungen",
        "Seit Montag erhält die Buchhaltung Mails mit angeblichen Rechnungen eines Lieferanten. "
        "Der Link im Anhang fragt nach den Zugangsdaten für das ERP-System.",
        goals="CI",
        origin=Origin.DELIBERATE_ATTACK,
        assets=("CI-0004", "CI-0001"),
    )
    # Only availability and technical failure: computed IT, stays IS until approved (M-04)
    _capture(
        melder,
        "Lüfter im Serverraum B ausgefallen",
        "In Rack 3 läuft ein Lüfter nicht mehr, die Temperatur steigt. Betroffen ist die "
        "Verfügbarkeit, ein Angriff ist nicht erkennbar.",
        goals="A",
        origin=Origin.TECHNICAL_FAILURE,
    )
    shared_login = _capture(
        melder,
        "Gemeinsames Konto an der Zeiterfassung",
        "Am Terminal in der Werkhalle melden sich alle Schichtleitungen mit demselben Konto an. "
        "Wer welche Buchung geändert hat, ist nicht nachvollziehbar.",
        goals="CI",
        origin=Origin.HUMAN_ERROR,
        assets=("CI-0011",),
    )
    services.score(shared_login, mueller, probability=3, impact=2)

    # --- reported by the risk managers ------------------------------------------------------
    ransomware = _capture(
        mueller,
        "Ransomware-Verdacht auf dem Dateiserver",
        "Auf dem Dateiserver der Fachbereiche tauchen seit heute Nacht Dateien mit der Endung "
        ".locked auf. Das letzte Backup ist von gestern 22 Uhr.",
        goals="CIA",
        origin=Origin.DELIBERATE_ATTACK,
        assets=("CI-0006", "CI-0009"),
    )
    services.score(ransomware, mueller, probability=5, impact=5)  # escalates, worker delivers

    vpn = _capture(
        mueller,
        "Ungepatchte VPN-Appliance",
        "Für die VPN-Appliance gibt es seit drei Wochen ein Update gegen eine aktiv ausgenutzte "
        "Schwachstelle, eingespielt ist es noch nicht. Angemeldet wird über das Active Directory.",
        goals="CI",
        origin=Origin.DELIBERATE_ATTACK,
        assets=("CI-0005",),
    )
    services.score(vpn, mueller, probability=4, impact=5)
    # The gateway is "down" for this escalation: dashboard flag and audit entry (AK-03.3)
    process_outbox(gateway=_Unreachable(), risk=vpn)

    payroll = _capture(
        mueller,
        "Gehaltsabrechnungen für alle lesbar freigegeben",
        "Ein Ordner mit Gehaltsabrechnungen war für alle Mitarbeitenden lesbar freigegeben. Seit "
        "wann, wird noch geprüft.",
        goals="C",
        origin=Origin.HUMAN_ERROR,
        assets=("CI-0002", "CI-0006"),
    )
    services.score(payroll, mueller, probability=4, impact=5)
    services.document_incident_response(
        payroll,
        ciso,
        "Freigabe am selben Tag entzogen, Zugriffsprotokolle gesichert, Datenschutzbeauftragte "
        "informiert. Laut Protokoll hat niemand außerhalb der Personalabteilung zugegriffen.",
    )

    brute_force = _capture(
        mueller,
        "Brute-Force-Versuche auf das Kundenportal",
        "Die Anmeldung am Kundenportal verzeichnet seit gestern mehrere tausend Fehlversuche aus "
        "wenigen IP-Bereichen.",
        goals="CI",
        origin=Origin.DELIBERATE_ATTACK,
        assets=("CI-0003",),
    )
    services.score(brute_force, mueller, probability=4, impact=5)
    # Downgrade below 20 after rate limiting: only a request, rm.schmidt decides (M-04)
    services.score(brute_force, mueller, probability=2, impact=5)

    printers = _capture(
        mueller,
        "Druckerverwaltung mit Standardpasswort",
        "Die Weboberfläche der Druckerverwaltung ist noch mit dem Passwort des Herstellers "
        "erreichbar, allerdings nur aus dem internen Netz.",
        goals="C",
        origin=Origin.HUMAN_ERROR,
        assets=("CI-0010",),
    )
    services.score(printers, mueller, probability=2, impact=1)
    transition(printers, RiskStatus.VALIDATED, mueller)

    disks = _capture(
        mueller,
        "Festplatten im Backup-System melden SMART-Fehler",
        "Zwei Platten im Backup-System melden Lesefehler. Ersatz ist bestellt, die Daten liegen "
        "noch gespiegelt vor.",
        goals="A",
        origin=Origin.TECHNICAL_FAILURE,
        assets=("CI-0009",),
    )
    services.decide(_pending(disks, ApprovalKind.CATEGORY_TO_IT), schmidt, approve=True)
    services.score(disks, mueller, probability=3, impact=4)
    transition(disks, RiskStatus.VALIDATED, mueller)
    transition(disks, RiskStatus.CLOSED, mueller)

    intranet = _capture(
        mueller,
        "Intranet ohne Zwei-Faktor-Anmeldung",
        "Das Intranet ist von außen nur mit Benutzername und Passwort erreichbar.",
        goals="CI",
        origin=Origin.DELIBERATE_ATTACK,
        assets=("CI-0008",),
    )
    services.score(intranet, mueller, probability=2, impact=2)
    transition(intranet, RiskStatus.VALIDATED, mueller)
    transition(intranet, RiskStatus.CLOSED, mueller)
    # Re-evaluation: CLOSED -> OBSOLETE always leaves a new DRAFT with a link to it
    transition(intranet, RiskStatus.OBSOLETE, mueller)

    mes = _capture(
        mueller,
        "Produktionsplanung ohne Netzsegmentierung",
        "Das MES steht im selben Netz wie die Büro-PCs. Ein kompromittierter Arbeitsplatz "
        "erreicht die Steuerung der Produktion direkt.",
        goals="IA",
        origin=Origin.DELIBERATE_ATTACK,
        assets=("CI-0007",),
    )
    services.score(mes, mueller, probability=3, impact=5)


def seed(users: Mapping[str, User]) -> int:
    """Create the demo register. Returns the number of risks, 0 if the register was not empty."""
    if Risk.objects.exists():
        return 0
    _build(users)
    return Risk.objects.count()
