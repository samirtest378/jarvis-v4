import asyncio
import sys
import types
from pathlib import Path

import pytest

import server


def test_local_speech_status_requires_both_engine_and_model(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(server, "SPEECH_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(server.shutil, "which", lambda _name: None)
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: tmp_path / "empty-home"))
    service = server.LocalSpeechRecognition()

    assert service.status()["available"] is False
    (tmp_path / ("whisper-server.exe" if server.sys.platform == "win32" else "whisper-server")).write_bytes(b"engine")
    assert service.status()["available"] is False
    (tmp_path / "ggml-base.bin").write_bytes(b"model")

    status = service.status()
    assert status["available"] is True
    assert status["local"] is True
    assert status["engine"] == "whisper.cpp"
    assert status["memory_budget_mb"] == 2560


def test_local_speech_refuses_models_that_can_break_the_memory_budget(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(server, "SPEECH_RUNTIME_DIR", tmp_path)
    monkeypatch.setattr(server.shutil, "which", lambda _name: None)
    monkeypatch.setattr(server.Path, "home", classmethod(lambda cls: tmp_path / "empty-home"))
    executable = tmp_path / ("whisper-server.exe" if server.sys.platform == "win32" else "whisper-server")
    executable.write_bytes(b"engine")
    model = tmp_path / "ggml-large-v3-turbo-q8_0.bin"
    with model.open("wb") as handle:
        handle.truncate(server.LocalSpeechRecognition.MAX_MODEL_BYTES + 1)

    status = server.LocalSpeechRecognition().status()

    assert status["available"] is False
    assert status["memory_budget_mb"] == 2560


def test_local_speech_rejects_non_wav_without_starting_engine():
    service = server.LocalSpeechRecognition()
    with pytest.raises(ValueError, match="PCM WAV"):
        asyncio.run(service.transcribe(b"not audio", "de-DE"))
    assert service.running is False


def test_local_speech_rejects_unsupported_language_without_starting_engine():
    service = server.LocalSpeechRecognition()
    wav_header = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 40
    with pytest.raises(ValueError, match="Unsupported speech language"):
        asyncio.run(service.transcribe(wav_header, "fr-FR"))
    assert service.running is False


def test_local_speech_stays_warm_only_while_listening(monkeypatch):
    service = server.LocalSpeechRecognition()
    started = False

    async def start():
        nonlocal started
        started = True

    monkeypatch.setattr(service, "_start", start)
    asyncio.run(service.prepare())
    assert started is True
    assert service._keep_warm is True

    service.release()
    assert service._keep_warm is False
    assert service._last_use > 0


@pytest.mark.parametrize(
    ("logical_cpus", "platform_name", "expected"),
    [
        (2, "win32", 2),
        (4, "win32", 3),
        (8, "win32", 6),
        (16, "win32", 8),
        (8, "darwin", 7),
    ],
)
def test_local_inference_reserves_capacity_for_the_interactive_app(
    logical_cpus: int,
    platform_name: str,
    expected: int,
):
    assert server._responsive_worker_threads(logical_cpus, platform_name) == expected


def test_windows_inference_job_uses_below_normal_priority():
    assert server.WINDOWS_JOB_OBJECT_LIMIT_PRIORITY_CLASS == 0x20
    assert server.WINDOWS_BELOW_NORMAL_PRIORITY_CLASS == 0x4000


def test_linux_local_speech_process_gets_the_same_hard_memory_limit(monkeypatch):
    captured = {}

    def prlimit(pid, resource_kind, limits):
        captured.update(pid=pid, resource_kind=resource_kind, limits=limits)

    fake_resource = types.SimpleNamespace(RLIMIT_AS=9, prlimit=prlimit)
    monkeypatch.setattr(server.sys, "platform", "linux")
    monkeypatch.setitem(sys.modules, "resource", fake_resource)

    assert server._apply_linux_process_memory_limit(4321, 2560 * 1024 * 1024) is True
    assert captured == {
        "pid": 4321,
        "resource_kind": 9,
        "limits": (2560 * 1024 * 1024, 2560 * 1024 * 1024),
    }
