"""Install the tested Apple-Silicon German video-voice sidecar safely."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-pack", required=True, type=Path)
    parser.add_argument("--voice-pack-root", required=True, type=Path)
    parser.add_argument("--profile-en", required=True, type=Path)
    parser.add_argument("--profile-de", required=True, type=Path)
    args = parser.parse_args()

    source = args.source_pack.expanduser().resolve()
    root = args.voice_pack_root.expanduser().resolve()
    profile_en = args.profile_en.expanduser().resolve()
    profile_de = args.profile_de.expanduser().resolve()
    manifest_path = source / "voice-pack.json"
    for required in (manifest_path, profile_en, profile_de):
        if not required.is_file():
            parser.error(f"required file does not exist: {required}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("engine_mode") != "moss-nano":
        parser.error("source pack is not a MOSS Nano voice pack")
    if manifest.get("platform") != "darwin" or manifest.get("arch") != "arm64":
        parser.error("this sidecar requires an Apple-Silicon voice pack")

    root.mkdir(parents=True, exist_ok=True)
    target = root / "multilingual"
    backup: Path | None = None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

    with tempfile.TemporaryDirectory(prefix="jarvis-moss-video-", dir=root) as temporary:
        staged = Path(temporary) / "multilingual"
        shutil.copytree(source, staged)
        shutil.copy2(profile_en, staged / "profile.safetensors")
        shutil.copy2(profile_de, staged / "profile-de.safetensors")

        staged_manifest_path = staged / "voice-pack.json"
        staged_manifest = json.loads(staged_manifest_path.read_text(encoding="utf-8"))
        staged_manifest.update({
            "name": "JARVIS v4 Reference-Video Voice",
            "version": "4.1.0-video-2026-08-01",
            "profile_source": "user-supplied 2026-08-01 reference video",
            "voice_identity": "Reference-video English JARVIS with language-matched German clone",
            "reference_audio_included": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
        staged_manifest["files"]["profile.safetensors"] = sha256(
            staged / "profile.safetensors"
        )
        staged_manifest["files"]["profile-de.safetensors"] = sha256(
            staged / "profile-de.safetensors"
        )
        staged_manifest_path.write_text(
            json.dumps(staged_manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

        if target.exists():
            backup = root / "backups" / f"{stamp}-multilingual"
            backup.parent.mkdir(parents=True, exist_ok=True)
            target.replace(backup)
        staged.replace(target)

    print(json.dumps({
        "installed": str(target),
        "backup": str(backup) if backup else None,
        "engine_mode": "moss-nano",
        "languages": ["de", "en"],
        "reference_audio_included": False,
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
