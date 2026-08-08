"""Reject a macOS voice pack that requires a newer OS than advertised."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


MACHO_MAGICS = {
    bytes.fromhex("feedface"),
    bytes.fromhex("feedfacf"),
    bytes.fromhex("cefaedfe"),
    bytes.fromhex("cffaedfe"),
    bytes.fromhex("cafebabe"),
    bytes.fromhex("bebafeca"),
    bytes.fromhex("cafebabf"),
    bytes.fromhex("bfbafeca"),
}


def _version_tuple(value: str) -> tuple[int, ...]:
    return tuple(int(part) for part in value.split("."))


def parse_minimum_versions(output: str) -> tuple[str, ...]:
    """Extract both modern and legacy macOS deployment targets from vtool."""
    modern = re.findall(
        r"cmd LC_BUILD_VERSION\b(?:(?!Load command).)*?\bminos\s+([0-9]+(?:\.[0-9]+)*)",
        output,
        flags=re.DOTALL,
    )
    legacy = re.findall(
        r"cmd LC_VERSION_MIN_MACOSX\b(?:(?!Load command).)*?\bversion\s+([0-9]+(?:\.[0-9]+)*)",
        output,
        flags=re.DOTALL,
    )
    return tuple(modern + legacy)


def _is_macho(path: Path) -> bool:
    try:
        with path.open("rb") as stream:
            return stream.read(4) in MACHO_MAGICS
    except OSError:
        return False


def verify_pack(pack_dir: Path, maximum: str) -> list[tuple[Path, str]]:
    maximum_tuple = _version_tuple(maximum)
    violations: list[tuple[Path, str]] = []
    inspected = 0
    for target in sorted(path for path in pack_dir.rglob("*") if path.is_file()):
        if not _is_macho(target):
            continue
        inspected += 1
        result = subprocess.run(
            ["vtool", "-show-build", str(target)],
            check=True,
            capture_output=True,
            text=True,
        )
        versions = parse_minimum_versions(result.stdout)
        if not versions:
            raise RuntimeError(f"Native file has no macOS deployment target: {target}")
        for version in versions:
            if _version_tuple(version) > maximum_tuple:
                violations.append((target, version))
    if inspected == 0:
        raise RuntimeError(f"No Mach-O files found in {pack_dir}")
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", required=True, type=Path)
    parser.add_argument("--maximum", default="14.0")
    args = parser.parse_args()
    pack_dir = args.pack_dir.expanduser().resolve()
    if not pack_dir.is_dir():
        parser.error(f"Voice-pack directory does not exist: {pack_dir}")
    violations = verify_pack(pack_dir, args.maximum)
    if violations:
        details = "\n".join(
            f"- {path.relative_to(pack_dir)} requires macOS {version}"
            for path, version in violations
        )
        raise SystemExit(
            f"macOS compatibility check failed; supported maximum is {args.maximum}:\n{details}"
        )
    print(f"macOS native compatibility verified at {args.maximum} or earlier")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
