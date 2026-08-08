"""Safely stage a verified JARVIS voice pack for installation or bundling."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


MAX_FILES = 20_000
MAX_BYTES = 8 * 1024 * 1024 * 1024
CRITICAL_HASHES = {
    "profile-en.npy": "276f750c643f95b2b6c6a0c82e90c9e6d0578661ab6fee240f8a128bbd57c75d",
    "profile-de.npy": "279ff6c17daa00db4cffe872a7a8a9c70814782077f0514c51c6851469d1b22a",
    "profiles.json": "b9a9cdbeb126920ec26dcf7b476e43d27b46871ec1cb8cccd1a4deb8d38dacfe",
    "models/neutts-nano-german-Q4_0.gguf": "c0a2e494d581afdac8f647f5b3c8644d6a0d793152d2f0387c860b92fcc1dd2b",
    "models/neutts-nano-Q4_0.gguf": "85466ca06aeb487e5e8d0263367166e125969e3f4b07245db009aee223702c86",
    "models/neucodec-int8.onnx": "3ddd9e56396e6029e0e948ac0255c89c803f981f23dcf4c154f50820bd74a6b3",
}
REQUIRED_COMMON_FILES = frozenset({
    "profile-en.npy",
    "profile-de.npy",
    "profiles.json",
    "models/neutts-nano-german-Q4_0.gguf",
    "models/neutts-nano-Q4_0.gguf",
    "models/neucodec-int8.onnx",
})
# Backward-compatible name used by the Windows installer tests.
REQUIRED_FILES = REQUIRED_COMMON_FILES | {"bin/jarvis-voice-engine.exe"}


def required_files(platform_name: str) -> frozenset[str]:
    executable = "jarvis-voice-engine.exe" if platform_name == "win32" else "jarvis-voice-engine"
    return REQUIRED_COMMON_FILES | {f"bin/{executable}"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def safe_member_name(raw: str) -> PurePosixPath:
    if "\\" in raw or "\0" in raw:
        raise ValueError("voice archive contains an unsafe path")
    name = PurePosixPath(raw.rstrip("/"))
    if not name.parts or name.is_absolute() or ".." in name.parts:
        raise ValueError("voice archive contains an unsafe path")
    return name


def stage_archive(
    archive_path: Path,
    output: Path,
    expected_platform: str = "win32",
    expected_arch: str = "x64",
    critical_hashes: dict[str, str] | None = None,
    expected_mastering: str = "reference-video-crisp-v1",
) -> dict[str, object]:
    critical_hashes = CRITICAL_HASHES if critical_hashes is None else critical_hashes
    with tempfile.TemporaryDirectory(prefix="jarvis-windows-voice-") as temporary:
        staging = Path(temporary)
        total_files = 0
        total_bytes = 0
        with zipfile.ZipFile(archive_path) as bundle:
            for info in bundle.infolist():
                name = safe_member_name(info.filename)
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("voice archive may not contain symbolic links")
                if info.is_dir():
                    continue
                total_files += 1
                total_bytes += info.file_size
                if total_files > MAX_FILES or total_bytes > MAX_BYTES:
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
            raise ValueError("voice archive is not the compact NeuTTS pack")
        if manifest.get("platform") != expected_platform or manifest.get("arch") != expected_arch:
            raise ValueError("voice archive targets the wrong platform")
        if set(manifest.get("languages", [])) != {"de", "en"}:
            raise ValueError("voice archive is not bilingual")
        if expected_mastering and manifest.get("mastering") != expected_mastering:
            raise ValueError("voice archive is missing the expected mastering")
        declared = manifest.get("files")
        if not isinstance(declared, dict) or not required_files(expected_platform).issubset(declared):
            raise ValueError("voice archive is incomplete")

        actual = {
            path.relative_to(root).as_posix(): path
            for path in root.rglob("*")
            if path.is_file() and path.name != "voice-pack.json"
        }
        if set(actual) != set(declared):
            raise ValueError("voice archive file list does not match its manifest")
        for relative, target in actual.items():
            expected = str(declared[relative]).lower()
            if len(expected) != 64 or sha256(target) != expected:
                raise ValueError(f"voice archive checksum failed: {relative}")
        for relative, expected in critical_hashes.items():
            if relative not in actual or sha256(actual[relative]) != expected:
                raise ValueError(f"voice identity does not match macOS: {relative}")

        if output.exists():
            shutil.rmtree(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(root), str(output))
        if expected_platform != "win32":
            engine = output / "bin" / "jarvis-voice-engine"
            engine.chmod(engine.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        return {
            "output": str(output.resolve()),
            "files": total_files,
            "bytes": total_bytes,
            "voice_identity": manifest.get("voice_identity", ""),
        }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--platform", default="win32")
    parser.add_argument("--arch", default="x64")
    args = parser.parse_args()
    result = stage_archive(args.archive.resolve(), args.output.resolve(), args.platform, args.arch)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
