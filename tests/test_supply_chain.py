"""M-02: third-party components are inventoried, pinned and checked against known
vulnerabilities; an SBOM in CycloneDX format can be produced at any time."""

import hashlib
import json
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.req("M-02")

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "src" / "static"
OWN_IMAGE = re.compile(r"^is-risk-classifier:")


def _manifest() -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads((STATIC / "third_party.json").read_text())
    return manifest


def test_m_02_python_dependencies_are_pinned_exactly() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    requirements = project["project"]["dependencies"] + project["dependency-groups"]["dev"]
    loose = [r for r in requirements if not re.fullmatch(r"[A-Za-z0-9_.\-\[\]]+==[\w.]+", r)]
    assert loose == []
    assert (ROOT / "uv.lock").is_file()


def test_m_02_container_images_are_pinned_by_digest() -> None:
    compose = (ROOT / "compose.yaml").read_text()
    images = re.findall(r"^\s*image:\s*(\S+)", compose, flags=re.M)
    assert images
    for image in images:
        assert OWN_IMAGE.match(image) or re.search(r":[\w.-]+@sha256:[0-9a-f]{64}$", image), image

    dockerfile = (ROOT / "docker" / "Dockerfile").read_text()
    for arg in re.findall(r"^ARG \w+_IMAGE=(\S+)", dockerfile, flags=re.M):
        assert re.search(r"@sha256:[0-9a-f]{64}$", arg), arg
    for add in re.findall(r"^ADD .*https://.*$", dockerfile, flags=re.M):
        assert "--checksum=sha256:" in add, add


def test_m_02_vendored_files_match_their_recorded_checksums() -> None:
    for component in _manifest()["components"]:
        digest = hashlib.sha256((STATIC / component["file"]).read_bytes()).hexdigest()
        assert digest == component["sha256"], component["file"]


def test_m_02_every_served_third_party_file_is_inventoried() -> None:
    listed = {c["file"] for c in _manifest()["components"]}
    served = {
        str(path.relative_to(STATIC))
        for folder in ("vendor", "fonts")
        for path in (STATIC / folder).iterdir()
        if path.suffix in {".js", ".woff2", ".css"}
    }
    assert served == listed


def test_m_02_tailwind_checksum_matches_the_dockerfile() -> None:
    tool = _manifest()["build_tools"][0]
    assert f"--checksum=sha256:{tool['sha256']}" in (ROOT / "docker" / "Dockerfile").read_text()


def test_m_02_sbom_lists_python_packages_front_end_files_and_images(tmp_path: Path) -> None:
    output = tmp_path / "sbom.cdx.json"
    subprocess.run(  # noqa: S603 - fixed command, no user input
        [sys.executable, str(ROOT / "tools" / "sbom.py"), "--output", str(output)],
        check=True,
        cwd=ROOT,
    )
    sbom = json.loads(output.read_text())

    assert (sbom["bomFormat"], sbom["specVersion"]) == ("CycloneDX", "1.5")
    purls = {c.get("purl", "") for c in sbom["components"]}
    assert "pkg:pypi/django@5.2.18" in purls
    assert "pkg:pypi/reportlab@5.0.1" in purls
    assert "pkg:npm/htmx.org@2.0.11" in purls
    assert any(p.startswith("pkg:docker/postgres@sha256%3A") for p in purls)
    assert any(
        p.startswith("pkg:docker/keycloak/keycloak@sha256%3A") and "repository_url=quay.io" in p
        for p in purls
    )
    # Runtime inventory only: test tooling does not ship
    assert not any(p.startswith("pkg:pypi/pytest@") for p in purls)
    hashes = {c["name"]: c["hashes"][0]["content"] for c in sbom["components"] if c.get("hashes")}
    assert hashes["htmx.org"] == _manifest()["components"][0]["sha256"]
