"""Create deterministic SHA-256 checksums for distributable JARVIS artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
RELEASE = ROOT / "release"
PACKAGE = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
VERSION = str(PACKAGE["version"])
SUPPORTED_SUFFIXES = {".dmg", ".zip", ".exe", ".appimage", ".deb", ".jarvisvoice"}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    artifacts = sorted(
        path
        for path in RELEASE.glob("JARVIS-v4-*")
        if (
            path.is_file()
            and VERSION in path.name
            and path.suffix.lower() in SUPPORTED_SUFFIXES
        )
    )
    if not artifacts:
        print(f"No JARVIS v4 {VERSION} release artifacts found in {RELEASE}")
        return 2

    output = RELEASE / f"JARVIS-v4-{VERSION}-SHA256SUMS.txt"
    content = "".join(f"{digest(path)}  {path.name}\n" for path in artifacts)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(output)
    print(f"Wrote {output} for {len(artifacts)} artifact(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
