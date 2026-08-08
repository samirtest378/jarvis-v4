"""Audit source-controlled requirements for a commercial JARVIS release."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONFIRMATION_FILES = {
    "commercial upstream license": "COMMERCIAL_LICENSE_CONFIRMATION.md",
    "JARVIS brand/trademark clearance": "BRAND_CLEARANCE_CONFIRMATION.md",
    "voice and reference-audio rights": "VOICE_RIGHTS_CONFIRMATION.md",
    "privacy, customer terms, and seller contact legal review": "PRIVACY_LEGAL_CONFIRMATION.md",
    "macOS Developer ID signing and notarization": "MACOS_SIGNING_CONFIRMATION.md",
    "clean-machine release QA": "RELEASE_QA_CONFIRMATION.md",
}
SECRET_PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-(?:api\d+-)?[A-Za-z0-9_-]{24,}"),
    "OpenAI key": re.compile(r"sk-(?:proj-)?[A-Za-z0-9_-]{32,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z_-]{30,}"),
}


def load_json(relative: str) -> dict:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def source_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    ignored_parts = {"node_modules", "release", "build", "dist", "dist-backend", ".venv"}
    return [
        ROOT / line
        for line in result.stdout.splitlines()
        if line and not ignored_parts.intersection(Path(line).parts) and (ROOT / line).is_file()
    ]


def human_release_blockers(root: Path = ROOT) -> list[str]:
    blockers: list[str] = []
    license_text = (root / "LICENSE").read_text(encoding="utf-8")
    if "COMMERCIAL USE PROHIBITED WITHOUT LICENSE" in license_text:
        blockers.append("the upstream license prohibits sale without a separate commercial license")

    for label, filename in CONFIRMATION_FILES.items():
        path = root / "docs" / filename
        if not path.is_file():
            blockers.append(f"missing verified {label} confirmation ({filename})")

    privacy_path = root / "docs" / "PRIVACY.md"
    if privacy_path.is_file():
        privacy_text = privacy_path.read_text(encoding="utf-8")
        if "Before sale, replace this section" in privacy_text:
            blockers.append("seller identity and privacy contact are still placeholders in PRIVACY.md")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strict", action="store_true", help="also require human legal/rights confirmations")
    args = parser.parse_args()
    errors: list[str] = []
    blockers: list[str] = []

    root_package = load_json("package.json")
    desktop_package = load_json("desktop/package.json")
    frontend_package = load_json("frontend/package.json")
    versions = {root_package.get("version"), desktop_package.get("version"), frontend_package.get("version")}
    if len(versions) != 1:
        errors.append(f"package versions are not synchronized: {sorted(str(value) for value in versions)}")

    build = desktop_package.get("build", {})
    mac = build.get("mac", {})
    nsis = build.get("nsis", {})
    if mac.get("notarize") is not True or mac.get("hardenedRuntime") is not True:
        errors.append("macOS notarization and Hardened Runtime are not both enabled")
    if build.get("win", {}).get("target", [{}])[0].get("target") != "nsis":
        errors.append("Windows NSIS target is not configured")
    if nsis.get("deleteAppDataOnUninstall") is not True:
        errors.append("Windows uninstall is not configured to remove private app data")

    required_files = [
        ".github/workflows/build-installers.yml",
        "docs/COMMERCIAL_RELEASE.md",
        "docs/PRIVACY.md",
        "requirements-build.lock.txt",
        "desktop/build/entitlements.mac.plist",
        "desktop/build/entitlements.mac.inherit.plist",
    ]
    for relative in required_files:
        if not (ROOT / relative).is_file():
            errors.append(f"required release file is missing: {relative}")

    for path in source_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in SECRET_PATTERNS.items():
            if pattern.search(content):
                errors.append(f"possible live {label} in {path.relative_to(ROOT)}")

    blockers.extend(human_release_blockers())

    if errors:
        print("RELEASE AUDIT: FAIL")
        for error in errors:
            print(f"  ERROR: {error}")
    else:
        print("RELEASE AUDIT: SOURCE CHECKS PASS")
    for blocker in blockers:
        print(f"  BLOCKER: {blocker}")
    if args.strict and blockers:
        print("STRICT COMMERCIAL RELEASE: NOT READY")
        return 2
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
