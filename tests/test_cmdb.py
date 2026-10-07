"""Decision 5: assets come from a CMDB CSV export; import updates, never deletes."""

from pathlib import Path

import pytest
from django.core.management import CommandError, call_command

from apps import cmdb
from apps.cmdb.models import Asset

pytestmark = pytest.mark.django_db


def _csv(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "assets.csv"
    path.write_text("cmdb_key,name,criticality\n" + body, encoding="utf-8")
    return path


def test_import_creates_and_updates(tmp_path: Path) -> None:
    call_command("import_assets", _csv(tmp_path, "CI-1,ERP,5\nCI-2,Intranet,2\n"))
    call_command("import_assets", _csv(tmp_path, "CI-1,ERP neu,4\n"))

    assert Asset.objects.count() == 2
    erp = Asset.objects.get(cmdb_key="CI-1")
    assert (erp.name, erp.criticality) == ("ERP neu", 4)


@pytest.mark.parametrize("criticality", ["0", "6", "hoch"])
def test_import_rejects_invalid_criticality(tmp_path: Path, criticality: str) -> None:
    with pytest.raises(CommandError):
        call_command("import_assets", _csv(tmp_path, f"CI-1,ERP,{criticality}\n"))
    assert not Asset.objects.exists()


def test_bundled_sample_data_imports() -> None:
    call_command("import_assets", Path(cmdb.__file__).parent / "data" / "assets.csv")
    assert Asset.objects.count() == 12
