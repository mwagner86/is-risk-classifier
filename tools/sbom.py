#!/usr/bin/env python
"""Write a CycloneDX 1.5 SBOM of what ships (M-02).

- Python packages: exported by uv from uv.lock, runtime dependencies only
- front-end files served locally: src/static/third_party.json (with SHA-256)
- build tools (Tailwind CLI, one binary per architecture): listed with scope "excluded", they
  never reach the browser
- container images: from compose.yaml and docker/Dockerfile, pinned by digest

Usage: python tools/sbom.py [--output sbom/is-risk-classifier.cdx.json]
"""

import argparse
import json
import re
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "src" / "static" / "third_party.json"
IMAGE = re.compile(r"(?P<repo>[\w./-]+):(?P<tag>[\w.-]+)@sha256:(?P<digest>[0-9a-f]{64})")


def python_bom() -> dict[str, Any]:
    result = subprocess.run(
        ["uv", "export", "--format", "cyclonedx1.5", "--frozen", "--no-dev"],  # noqa: S607
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    bom: dict[str, Any] = json.loads(result.stdout)
    return bom


def front_end_components() -> list[dict[str, Any]]:
    manifest = json.loads(MANIFEST.read_text())
    components = []
    for entry, kind, scope in [
        *[(c, "library", "required") for c in manifest["components"]],
        *[(c, "application", "excluded") for c in manifest["build_tools"]],
    ]:
        components.append(
            {
                "type": kind,
                "bom-ref": entry["purl"],
                "name": entry["name"],
                "version": entry["version"],
                "scope": scope,
                "purl": entry["purl"],
                "licenses": [{"license": {"id": entry["license"]}}],
                "hashes": [{"alg": "SHA-256", "content": entry["sha256"]}],
            }
        )
    return components


def _docker_purl(repo: str, digest: str) -> tuple[str, str]:
    """purl per the spec: registry as repository_url, Docker Hub images without namespace."""
    parts = repo.split("/")
    registry = parts[0] if len(parts) > 1 and ("." in parts[0] or ":" in parts[0]) else ""
    name = "/".join(parts[1:] if registry else parts)
    purl = f"pkg:docker/{name}@{quote(f'sha256:{digest}', safe='')}"
    if registry:
        purl += f"?repository_url={registry}"
    return name, purl


def image_components() -> list[dict[str, Any]]:
    sources = (ROOT / "compose.yaml").read_text() + (ROOT / "docker" / "Dockerfile").read_text()
    seen: dict[str, dict[str, Any]] = {}
    for match in IMAGE.finditer(sources):
        name, purl = _docker_purl(match["repo"], match["digest"])
        seen[purl] = {
            "type": "container",
            "bom-ref": purl,
            "name": name,
            "version": match["tag"],
            "purl": purl,
            "hashes": [{"alg": "SHA-256", "content": match["digest"]}],
        }
    return list(seen.values())


def build() -> dict[str, Any]:
    bom = python_bom()
    bom["serialNumber"] = f"urn:uuid:{uuid.uuid4()}"
    bom.setdefault("metadata", {})["timestamp"] = datetime.now(UTC).isoformat(timespec="seconds")
    bom["components"] = bom.get("components", []) + front_end_components() + image_components()
    return bom


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--output", type=Path, default=ROOT / "sbom" / "is-risk-classifier.cdx.json"
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bom = build()
    args.output.write_text(json.dumps(bom, indent=2, ensure_ascii=False) + "\n")
    print(f"{args.output}: {len(bom['components'])} components")


if __name__ == "__main__":
    main()
