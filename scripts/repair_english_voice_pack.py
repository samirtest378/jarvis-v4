"""Put the English Turbo pack back into `voice-pack/current`.

While the German voice was being built, `voice-pack/current` was left in a
mixed state: a manifest declaring the multilingual engine, the cloned German
speaker profile, and in one install the multilingual weights on top of the
English ones. A pack in that state cannot start at all — the backend looks for
the multilingual model files the manifest promises and finds Turbo weights.

This restores the intended split:

    voice-pack/current       English only, fast   (Chatterbox Turbo)
    voice-pack/multilingual  German + English     (Chatterbox Multilingual)

The Turbo weights and the original English speaker profile are taken from a
reference pack — by default the untouched JARVIS v2 install. Only
`voice-pack/current` is written; the bilingual pack is never touched.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

TURBO_MODEL_FILES = (
    "t3_turbo_v1.safetensors",
    "s3gen_meanflow.safetensors",
    "ve.safetensors",
    "conds.pt",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.json",
    "merges.txt",
)

# Left behind when the multilingual weights were downloaded over this pack.
MULTILINGUAL_MODEL_FILES = (
    "ve.pt",
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
)

SUPPORT = Path.home() / "Library/Application Support"
DEFAULT_SOURCE = SUPPORT / "jarvis-v2-desktop/voice-pack/current"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repair(pack: Path, source: Path, version: str) -> bool:
    if not (pack / "bin").is_dir():
        print(f"skipping {pack}: no pack installed there")
        return False

    models = pack / "models"
    models.mkdir(parents=True, exist_ok=True)

    restored = []
    for name in TURBO_MODEL_FILES:
        target = models / name
        origin = source / "models" / name
        if target.is_file() and sha256(target) == sha256(origin):
            continue
        shutil.copy2(origin, target)
        restored.append(name)

    removed = []
    for name in MULTILINGUAL_MODEL_FILES:
        stray = models / name
        if stray.is_file():
            stray.unlink()
            removed.append(name)

    profile = pack / "profile.pt"
    profile_restored = not profile.is_file() or sha256(profile) != sha256(source / "profile.pt")
    if profile_restored:
        shutil.copy2(source / "profile.pt", profile)

    # Recompute every checksum: the file list is what a `.jarvisvoice` install
    # verifies, so a stale entry would reject a pack that is actually fine.
    files = {
        path.relative_to(pack).as_posix(): sha256(path)
        for path in sorted(pack.rglob("*"))
        if path.is_file() and path.name != "voice-pack.json"
    }
    manifest = {
        "format_version": 1,
        "name": "JARVIS v4 English Voice",
        "version": version,
        "platform": "darwin",
        "arch": "arm64",
        "engine": "ResembleAI Chatterbox Turbo 0.1.7",
        "engine_mode": "turbo",
        "model": "ResembleAI/chatterbox-turbo",
        "languages": ["en"],
        "license": "MIT",
        "profile_source": "derived-from-user-supplied-video",
        "reference_audio_included": False,
        "watermark": "Perth implicit audio watermark enabled",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    (pack / "voice-pack.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    print(f"repaired {pack}")
    print(f"  models restored: {', '.join(restored) if restored else 'none needed'}")
    print(f"  stray multilingual files removed: {', '.join(removed) if removed else 'none'}")
    print(f"  English speaker profile restored: {'yes' if profile_restored else 'already correct'}")
    print(f"  checksums written for {len(files)} files")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--targets", nargs="+", default=["JARVIS v4", "jarvis-v4-desktop"])
    parser.add_argument("--version", default="0.7.21")
    args = parser.parse_args()

    missing = [
        name for name in (*TURBO_MODEL_FILES, "../profile.pt")
        if not (args.source / "models" / name).resolve().is_file()
    ]
    if missing:
        print(f"reference pack incomplete: {args.source}", file=sys.stderr)
        print(f"  missing: {', '.join(missing)}", file=sys.stderr)
        return 2

    repaired = 0
    for name in args.targets:
        if repair(SUPPORT / name / "voice-pack" / "current", args.source, args.version):
            repaired += 1
    if not repaired:
        print("nothing repaired", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
