"""Prepare verified NeuTTS model files for a native voice-pack build.

The source archive supplies only the platform-independent model weights.  The
native engine and eSpeak runtime are rebuilt on the target operating system.
"""

from __future__ import annotations

import argparse
import json
import shutil
import stat
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from scripts.stage_bundled_voice_pack import (
    CRITICAL_HASHES,
    MAX_BYTES,
    MAX_FILES,
    safe_member_name,
    sha256,
)


MODEL_FILES = (
    "neutts-nano-german-Q4_0.gguf",
    "neutts-nano-Q4_0.gguf",
    "neucodec-int8.onnx",
    "NEUTTS_MODEL_LICENSE.txt",
)
ESPEAK_LIBRARY_NAMES = {
    "darwin": "libespeak-ng.1.52.0.1.dylib",
    "linux": "libespeak-ng.so.1",
    "win32": "espeak-ng.dll",
}


def prepare_models(archive: Path, output: Path, platform_name: str) -> dict[str, object]:
    import espeakng_loader

    if platform_name not in ESPEAK_LIBRARY_NAMES:
        raise ValueError(f"unsupported target platform: {platform_name}")
    with tempfile.TemporaryDirectory(prefix="jarvis-voice-models-") as temporary:
        staging = Path(temporary)
        file_count = 0
        byte_count = 0
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                name = safe_member_name(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("voice archive may not contain symbolic links")
                if info.is_dir():
                    continue
                file_count += 1
                byte_count += info.file_size
                if file_count > MAX_FILES or byte_count > MAX_BYTES:
                    raise ValueError("voice archive exceeds the safety limit")
                target = staging.joinpath(*name.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(info) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination, length=8 * 1024 * 1024)

        manifests = list(staging.glob("*/voice-pack.json"))
        if len(manifests) != 1:
            raise ValueError("voice archive must contain exactly one pack")
        root = manifests[0].parent
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        if manifest.get("format_version") != 1 or manifest.get("engine_mode") != "neutts-nano":
            raise ValueError("base archive is not a NeuTTS voice pack")
        declared = manifest.get("files")
        if not isinstance(declared, dict):
            raise ValueError("base archive checksums are missing")
        actual = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file() and path.name != "voice-pack.json"
        }
        if set(actual) != set(declared):
            raise ValueError("base archive file list does not match its manifest")
        for relative, target in actual.items():
            expected = str(declared[relative]).lower()
            if len(expected) != 64 or sha256(target) != expected:
                raise ValueError(f"base archive checksum failed: {relative}")
        for relative, expected in CRITICAL_HASHES.items():
            if not relative.startswith("models/"):
                continue
            target = root / relative
            if not target.is_file() or sha256(target) != expected:
                raise ValueError(f"base model identity failed: {relative}")

        if output.exists():
            shutil.rmtree(output)
        output.mkdir(parents=True)
        for name in MODEL_FILES:
            source = root / "models" / name
            if not source.is_file():
                raise ValueError(f"base model is incomplete: {name}")
            shutil.copy2(source, output / name)

    library = Path(espeakng_loader.get_library_path())
    data = Path(espeakng_loader.get_data_path())
    if not library.is_file() or not data.is_dir():
        raise RuntimeError("the native eSpeak NG runtime is incomplete")
    espeak = output / "espeak"
    espeak.mkdir(parents=True)
    shutil.copy2(library, espeak / ESPEAK_LIBRARY_NAMES[platform_name])
    shutil.copytree(data, espeak / "espeak-ng-data")
    return {
        "output": str(output.resolve()),
        "platform": platform_name,
        "model_hashes": {
            name: sha256(output / name)
            for name in MODEL_FILES
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--platform", required=True, choices=tuple(ESPEAK_LIBRARY_NAMES))
    args = parser.parse_args()
    result = prepare_models(args.archive.resolve(), args.output.resolve(), args.platform)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
