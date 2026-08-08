from __future__ import annotations

import hashlib
import json
import os
import zipfile
from pathlib import Path

import pytest

from scripts.stage_bundled_voice_pack import REQUIRED_FILES, safe_member_name, stage_archive


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_test_pack(path: Path, platform: str = "win32") -> None:
    files = {name: f"test:{name}".encode() for name in REQUIRED_FILES}
    manifest = {
        "format_version": 1,
        "engine_mode": "neutts-nano",
        "platform": platform,
        "arch": "x64",
        "languages": ["de", "en"],
        "voice_identity": "shared test voice",
        "mastering": "reference-video-crisp-v1",
        "files": {name: _sha(data) for name, data in files.items()},
    }
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(f"JARVIS-voice/{name}", data)
        bundle.writestr("JARVIS-voice/voice-pack.json", json.dumps(manifest))


def test_windows_voice_pack_is_staged_only_after_manifest_verification(tmp_path: Path):
    archive = tmp_path / "voice.jarvisvoice"
    output = tmp_path / "bundled"
    _write_test_pack(archive)

    result = stage_archive(archive, output, critical_hashes={})

    assert result["voice_identity"] == "shared test voice"
    assert (output / "bin" / "jarvis-voice-engine.exe").is_file()
    assert json.loads((output / "voice-pack.json").read_text())["platform"] == "win32"


def test_mac_voice_pack_uses_the_native_engine_name(tmp_path: Path):
    archive = tmp_path / "voice-mac.jarvisvoice"
    output = tmp_path / "mac"
    files = {
        name.replace("jarvis-voice-engine.exe", "jarvis-voice-engine"): f"test:{name}".encode()
        for name in REQUIRED_FILES
    }
    manifest = {
        "format_version": 1,
        "engine_mode": "neutts-nano",
        "platform": "darwin",
        "arch": "arm64",
        "languages": ["de", "en"],
        "voice_identity": "shared test voice",
        "mastering": "reference-video-crisp-v1",
        "files": {name: _sha(data) for name, data in files.items()},
    }
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(f"JARVIS-voice/{name}", data)
        bundle.writestr("JARVIS-voice/voice-pack.json", json.dumps(manifest))

    stage_archive(archive, output, "darwin", "arm64", critical_hashes={})

    assert (output / "bin" / "jarvis-voice-engine").is_file()
    assert os.access(output / "bin" / "jarvis-voice-engine", os.X_OK)


def test_wrong_platform_and_unsafe_paths_are_rejected(tmp_path: Path):
    archive = tmp_path / "wrong.jarvisvoice"
    _write_test_pack(archive, platform="darwin")
    with pytest.raises(ValueError, match="wrong platform"):
        stage_archive(archive, tmp_path / "out", critical_hashes={})
    for name in ("../voice", "/absolute/voice", "folder\\voice"):
        with pytest.raises(ValueError, match="unsafe path"):
            safe_member_name(name)
