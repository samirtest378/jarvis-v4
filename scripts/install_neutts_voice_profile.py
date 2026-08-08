"""Safely activate updated NeuTTS profiles in an unpacked JARVIS voice pack."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", required=True, type=Path)
    parser.add_argument("--profile-en", required=True, type=Path)
    parser.add_argument("--profile-de", required=True, type=Path)
    parser.add_argument("--profiles", required=True, type=Path)
    args = parser.parse_args()

    pack = args.pack_dir.expanduser().resolve()
    profile_en = args.profile_en.expanduser().resolve()
    profile_de = args.profile_de.expanduser().resolve()
    metadata = args.profiles.expanduser().resolve()
    manifest_path = pack / "voice-pack.json"
    current_profile_en = pack / "profile-en.npy"
    current_profile_de = pack / "profile-de.npy"
    current_metadata = pack / "profiles.json"
    for required in (
        manifest_path,
        current_profile_en,
        current_profile_de,
        current_metadata,
        profile_en,
        profile_de,
        metadata,
    ):
        if not required.is_file():
            parser.error(f"required file does not exist: {required}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    profiles = json.loads(metadata.read_text(encoding="utf-8"))
    codes_en = np.load(profile_en, allow_pickle=False)
    codes_de = np.load(profile_de, allow_pickle=False)
    if (
        manifest.get("engine_mode") != "neutts-nano"
        or codes_en.dtype != np.int32
        or codes_de.dtype != np.int32
        or codes_en.ndim != 1
        or codes_de.ndim != 1
    ):
        parser.error("the target pack or profile is not compatible with NeuTTS")
    if (
        int(profiles.get("en", {}).get("codes", -1)) != int(codes_en.size)
        or int(profiles.get("de", {}).get("codes", -1)) != int(codes_de.size)
    ):
        parser.error("profile metadata does not match the encoded profiles")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = pack.parent / "backups" / stamp
    backup.mkdir(parents=True, exist_ok=False)
    for source in (current_profile_en, current_profile_de, current_metadata, manifest_path):
        shutil.copy2(source, backup / source.name)

    with tempfile.TemporaryDirectory(prefix="jarvis-voice-profile-", dir=pack.parent) as temporary:
        temp = Path(temporary)
        staged_profile_en = temp / "profile-en.npy"
        staged_profile_de = temp / "profile-de.npy"
        staged_metadata = temp / "profiles.json"
        shutil.copy2(profile_en, staged_profile_en)
        shutil.copy2(profile_de, staged_profile_de)
        shutil.copy2(metadata, staged_metadata)

        manifest["profile_source"] = "user-supplied 2026-08-01 reference video"
        manifest["voice_identity"] = "JARVIS V3 Old Reference and Tuned 1"
        manifest["profile_language"] = "de,en"
        manifest["reference_audio_included"] = False
        manifest["updated_at"] = datetime.now(timezone.utc).isoformat()
        manifest["files"]["profile-en.npy"] = sha256(staged_profile_en)
        manifest["files"]["profile-de.npy"] = sha256(staged_profile_de)
        manifest["files"]["profiles.json"] = sha256(staged_metadata)
        staged_manifest = temp / "voice-pack.json"
        staged_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

        staged_profile_en.replace(current_profile_en)
        staged_profile_de.replace(current_profile_de)
        staged_metadata.replace(current_metadata)
        staged_manifest.replace(manifest_path)

    print(json.dumps({
        "pack": str(pack),
        "backup": str(backup),
        "english_codes": int(codes_en.size),
        "german_codes": int(codes_de.size),
        "german_profile_updated": True,
        "reference_audio_included": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
