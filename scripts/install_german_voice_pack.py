"""Assemble the bilingual voice pack from the cloned German profile.

The English pack stays exactly where it is. This builds a second pack beside it
that runs the multilingual engine, so the app can be pointed at either one:

    voice-pack/current       English only, fast   (Chatterbox Turbo)
    voice-pack/multilingual  German + English     (Chatterbox Multilingual)

Both share the same engine binary — it already accepts `--mode multilingual`.
Only the model files, the speaker profile and the manifest differ.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODEL_SOURCE = ROOT / "build" / "mtl-model"
PROFILE_SOURCE = ROOT / "build" / "german-voice" / "german-profile.pt"

MODEL_FILES = (
    "ve.pt",
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
)


def voice_pack_root(app_support_name: str) -> Path:
    return Path.home() / "Library/Application Support" / app_support_name / "voice-pack"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["JARVIS v4", "jarvis-v4-desktop"],
        help="Application Support directories to install into",
    )
    args = parser.parse_args()

    if not PROFILE_SOURCE.is_file():
        print(f"German profile missing: {PROFILE_SOURCE}", file=sys.stderr)
        print("Run scripts/build_german_voice.py first.", file=sys.stderr)
        return 2
    missing = [name for name in MODEL_FILES if not (MODEL_SOURCE / name).is_file()]
    if missing:
        print(f"multilingual model incomplete in {MODEL_SOURCE}: {', '.join(missing)}", file=sys.stderr)
        return 2

    installed = 0
    for name in args.targets:
        packs = voice_pack_root(name)
        english = packs / "current"
        if not (english / "bin").is_dir():
            print(f"skipping {name}: no English pack to take the engine from", file=sys.stderr)
            continue

        target = packs / "multilingual"
        if target.exists():
            shutil.rmtree(target)
        (target / "models").mkdir(parents=True)

        # The engine binary is identical for both modes.
        shutil.copytree(english / "bin", target / "bin")
        for filename in MODEL_FILES:
            shutil.copy2(MODEL_SOURCE / filename, target / "models" / filename)
        shutil.copy2(PROFILE_SOURCE, target / "profile.pt")
        for extra in ("README.txt", "THIRD_PARTY_NOTICES.md", "licenses"):
            source = english / extra
            if source.is_dir():
                shutil.copytree(source, target / extra)
            elif source.is_file():
                shutil.copy2(source, target / extra)

        english_manifest = json.loads((english / "voice-pack.json").read_text(encoding="utf-8"))
        manifest = {
            "format_version": english_manifest.get("format_version", 1),
            "name": "JARVIS Bilingual Voice (German & English)",
            "version": "1.0.0",
            "platform": english_manifest.get("platform", "darwin"),
            "arch": english_manifest.get("arch", "arm64"),
            "engine": "ResembleAI Chatterbox Multilingual",
            "engine_mode": "multilingual",
            "languages": ["de", "en"],
            "model": "ResembleAI/chatterbox",
            "license": english_manifest.get("license", "MIT"),
            "profile_source": "cloned-from-the-english-jarvis-voice",
            "reference_audio_included": False,
            "watermark": "Perth implicit audio watermark enabled",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        (target / "voice-pack.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )

        size = sum(f.stat().st_size for f in target.rglob("*") if f.is_file()) / 1_000_000_000
        print(f"installed bilingual pack for {name} ({size:.1f} GB) -> {target}")
        installed += 1

    if not installed:
        print("nothing installed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
