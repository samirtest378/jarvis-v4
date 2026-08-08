from __future__ import annotations

import hashlib
import json
import sys
import types
import zipfile
from pathlib import Path

import scripts.prepare_cross_platform_voice as prepare


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def test_prepare_models_replaces_platform_runtime_and_keeps_verified_weights(
    tmp_path: Path,
    monkeypatch,
) -> None:
    files = {
        "models/neutts-nano-german-Q4_0.gguf": b"german-model",
        "models/neutts-nano-Q4_0.gguf": b"english-model",
        "models/neucodec-int8.onnx": b"decoder",
        "models/NEUTTS_MODEL_LICENSE.txt": b"license",
        "bin/jarvis-voice-engine": b"old-native-engine",
    }
    manifest = {
        "format_version": 1,
        "engine_mode": "neutts-nano",
        "files": {name: _sha(data) for name, data in files.items()},
    }
    archive = tmp_path / "base.jarvisvoice"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name, data in files.items():
            bundle.writestr(f"base/{name}", data)
        bundle.writestr("base/voice-pack.json", json.dumps(manifest))

    library = tmp_path / "libespeak.dylib"
    library.write_bytes(b"native-espeak")
    data = tmp_path / "espeak-data"
    data.mkdir()
    (data / "phondata").write_bytes(b"phonemes")
    monkeypatch.setitem(
        sys.modules,
        "espeakng_loader",
        types.SimpleNamespace(
            get_library_path=lambda: library,
            get_data_path=lambda: data,
        ),
    )
    monkeypatch.setattr(
        prepare,
        "CRITICAL_HASHES",
        {name: _sha(contents) for name, contents in files.items() if name.startswith("models/")},
    )

    output = tmp_path / "prepared"
    result = prepare.prepare_models(archive, output, "darwin")

    assert result["platform"] == "darwin"
    assert (output / "neutts-nano-Q4_0.gguf").read_bytes() == b"english-model"
    assert (output / "espeak" / "libespeak-ng.1.52.0.1.dylib").read_bytes() == b"native-espeak"
    assert (output / "espeak" / "espeak-ng-data" / "phondata").read_bytes() == b"phonemes"
    assert not (output / "jarvis-voice-engine").exists()
