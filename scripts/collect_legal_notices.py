"""Collect customer documents and third-party license evidence for installers."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import re
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "desktop" / "legal-dist"
LOCKFILE = ROOT / "requirements-build.lock.txt"
LICENSE_NAME = re.compile(r"^(licen[cs]e|copying|notice|copyright)(?:[._-].*)?$", re.IGNORECASE)
REQUIRED_PYTHON = {
    "anthropic",
    "fastapi",
    "httpx",
    "playwright",
    "pydantic",
    "pyyaml",
    "uvicorn",
    "websockets",
}
REQUIRED_NODE = {"electron", "extract-zip", "three"}
CUSTOMER_DOCUMENTS = {
    ROOT / "LICENSE": "JARVIS_LICENSE.txt",
    ROOT / "docs" / "PRIVACY.md": "PRIVACY.md",
    ROOT / "docs" / "SUPPORT.md": "SUPPORT.md",
    ROOT / "docs" / "USER_GUIDE.md": "USER_GUIDE.md",
    ROOT / "local_voice" / "THIRD_PARTY_NOTICES.md": "VOICE_THIRD_PARTY_NOTICES.md",
    LOCKFILE: "PYTHON_BUILD_LOCK.txt",
}


def canonical(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def locked_python_names(lockfile: Path = LOCKFILE) -> set[str]:
    names: set[str] = set()
    for line in lockfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^([A-Za-z0-9_.-]+)==", line)
        if match:
            names.add(canonical(match.group(1)))
    return names


def license_candidates(files: list[Path] | None) -> list[Path]:
    return [
        item
        for item in files or []
        if LICENSE_NAME.match(Path(item).name)
    ]


def collect_python_notices(target: Path) -> list[dict]:
    locked = locked_python_names()
    records: list[dict] = []
    found: set[str] = set()
    for distribution in importlib.metadata.distributions():
        metadata = distribution.metadata
        raw_name = metadata.get("Name") or ""
        name = canonical(raw_name)
        if not name or name not in locked or name in found:
            continue
        found.add(name)
        version = distribution.version
        license_value = (
            metadata.get("License-Expression")
            or metadata.get("License")
            or "Not declared in package metadata"
        ).strip()
        component_dir = target / f"{name}-{version}"
        copied: list[str] = []
        for index, relative in enumerate(license_candidates(distribution.files)):
            source = Path(distribution.locate_file(relative))
            if not source.is_file() or source.stat().st_size > 2 * 1024 * 1024:
                continue
            component_dir.mkdir(parents=True, exist_ok=True)
            destination = component_dir / f"{index + 1:02d}-{source.name}"
            shutil.copy2(source, destination)
            copied.append(destination.relative_to(OUTPUT).as_posix())
        records.append(
            {
                "ecosystem": "PyPI",
                "name": raw_name or name,
                "version": version,
                "license": license_value,
                "homepage": metadata.get("Home-page") or metadata.get("Project-URL") or "",
                "license_files": copied,
            }
        )

    missing = sorted(REQUIRED_PYTHON - found)
    if missing:
        raise RuntimeError(f"Required Python license metadata is unavailable: {', '.join(missing)}")
    return sorted(records, key=lambda item: canonical(item["name"]))


def npm_package_paths(project: Path) -> list[Path]:
    # ``npm`` is a shell shim on Unix, while the executable Windows can launch
    # directly is ``npm.cmd``. Resolve the real command first so Python does
    # not depend on shell-specific PATHEXT behaviour during installer builds.
    npm = shutil.which("npm.cmd") or shutil.which("npm")
    if not npm:
        raise RuntimeError("npm is required to collect bundled Node.js licenses")
    result = subprocess.run(
        [npm, "ls", "--omit=dev", "--all", "--parseable"],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
    )
    return [Path(line) for line in result.stdout.splitlines()[1:] if line.strip()]


def collect_node_notices(target: Path) -> list[dict]:
    package_paths = {
        *npm_package_paths(ROOT / "desktop"),
        *npm_package_paths(ROOT / "frontend"),
        ROOT / "desktop" / "node_modules" / "electron",
        ROOT / "frontend" / "node_modules" / "three",
    }
    records: list[dict] = []
    found: set[str] = set()
    licensed_required: set[str] = set()
    for package_dir in sorted(package_paths):
        manifest_path = package_dir / "package.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        raw_name = str(manifest.get("name") or package_dir.name)
        name = canonical(raw_name)
        version = str(manifest.get("version") or "")
        identity = f"{name}@{version}"
        if identity in found:
            continue
        found.add(identity)
        component_dir = target / f"{name}-{version}"
        copied: list[str] = []
        for index, source in enumerate(
            item for item in package_dir.iterdir()
            if item.is_file() and LICENSE_NAME.match(item.name)
        ):
            component_dir.mkdir(parents=True, exist_ok=True)
            destination = component_dir / f"{index + 1:02d}-{source.name}"
            shutil.copy2(source, destination)
            copied.append(destination.relative_to(OUTPUT).as_posix())
        if name in REQUIRED_NODE and copied:
            licensed_required.add(name)
        records.append(
            {
                "ecosystem": "npm",
                "name": raw_name,
                "version": version,
                "license": manifest.get("license") or "Not declared in package metadata",
                "homepage": manifest.get("homepage") or "",
                "license_files": copied,
            }
        )

    missing = sorted(REQUIRED_NODE - licensed_required)
    if missing:
        raise RuntimeError(f"Required Node license files are unavailable: {', '.join(missing)}")
    return sorted(records, key=lambda item: canonical(item["name"]))


def main() -> int:
    shutil.rmtree(OUTPUT, ignore_errors=True)
    OUTPUT.mkdir(parents=True)

    for source, filename in CUSTOMER_DOCUMENTS.items():
        if not source.is_file():
            raise RuntimeError(f"Required customer document is missing: {source}")
        shutil.copy2(source, OUTPUT / filename)

    components = [
        *collect_python_notices(OUTPUT / "third-party" / "python"),
        *collect_node_notices(OUTPUT / "third-party" / "node"),
    ]
    manifest = {
        "schema": 1,
        "product": "JARVIS v4",
        "components": components,
    }
    manifest_path = OUTPUT / "THIRD_PARTY_COMPONENTS.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    inventory = []
    for path in sorted(item for item in OUTPUT.rglob("*") if item.is_file()):
        inventory.append(
            {
                "path": path.relative_to(OUTPUT).as_posix(),
                "sha256": sha256(path),
                "size": path.stat().st_size,
            }
        )
    (OUTPUT / "LEGAL_INVENTORY.json").write_text(
        json.dumps({"schema": 1, "files": inventory}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"Collected {len(components)} third-party components in {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
