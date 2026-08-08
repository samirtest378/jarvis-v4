"""The language switch decides which cloned JARVIS voice pack speaks.

Two packs can be installed side by side — the English-only Turbo pack that
ships with the app and a bilingual one carrying the same voice cloned into a
model that also speaks German. The user only ever picks a language; the pack
follows from it.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import server


def _auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {server.JARVIS_AUTH_TOKEN}"}


def _install_packs(tmp_path, bilingual: bool = True, current_mode: str = "turbo"):
    """Lay out both packs the way an install does, manifests only."""
    root = tmp_path / "voice-pack"
    english = root / "current"
    english.mkdir(parents=True)
    current_languages = (
        ["de", "en"]
        if current_mode in {"moss-nano", "neutts-nano"}
        else ["en"]
    )
    (english / "voice-pack.json").write_text(
        json.dumps({
            "format_version": 1,
            "engine_mode": current_mode,
            "languages": current_languages,
        }),
        encoding="utf-8",
    )
    if bilingual:
        german = root / "multilingual"
        german.mkdir(parents=True)
        (german / "voice-pack.json").write_text(
            json.dumps({"format_version": 1, "engine_mode": "multilingual", "languages": ["de", "en"]}),
            encoding="utf-8",
        )
    return english


@pytest.fixture
def packs(tmp_path, monkeypatch):
    english = _install_packs(tmp_path)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", english)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_OVERRIDE", False)
    return english


@pytest.mark.parametrize(
    "language, expected",
    [
        ("en-GB", "current"),
        ("en-US", "current"),
        ("de-DE", "multilingual"),
        ("auto", "multilingual"),
    ],
)
def test_language_setting_picks_the_pack_that_can_speak_it(packs, monkeypatch, language, expected):
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", language)
    assert server._local_voice_pack_dir().name == expected


def test_english_only_keeps_the_faster_pack(packs, monkeypatch):
    """Measured: the multilingual model is far slower, so English must not use it."""
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "en-GB")
    assert server._local_voice_mode() == "turbo"
    assert server._local_voice_languages() == frozenset({"en"})


def test_german_reports_both_languages(packs, monkeypatch):
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "de-DE")
    assert server._local_voice_mode() == "multilingual"
    assert server._local_voice_languages() == frozenset({"de", "en"})


@pytest.mark.parametrize("mode", ["moss-nano", "neutts-nano"])
@pytest.mark.parametrize("language", ["auto", "de-DE", "en-US", "en-GB"])
def test_compact_bilingual_current_pack_wins_for_every_language(
    tmp_path,
    monkeypatch,
    language,
    mode,
):
    current = _install_packs(tmp_path, current_mode=mode)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", current)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_OVERRIDE", False)
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", language)

    assert server._local_voice_pack_dir() == current
    assert server._local_voice_mode() == mode
    assert server._local_voice_languages() == frozenset({"de", "en"})


def test_compact_current_pack_keeps_the_same_voice_for_german_and_english(tmp_path, monkeypatch):
    current = _install_packs(tmp_path, current_mode="neutts-nano")
    sidecar = current.parent / "multilingual"
    (sidecar / "voice-pack.json").write_text(
        json.dumps({
            "format_version": 1,
            "engine_mode": "moss-nano",
            "languages": ["de", "en"],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", current)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_OVERRIDE", False)
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "auto")

    assert server._local_voice_pack_dir("en") == current
    assert server._local_voice_mode("en") == "neutts-nano"
    assert server._local_voice_pack_dir("de") == current
    assert server._local_voice_mode("de") == "neutts-nano"


@pytest.mark.asyncio
async def test_resident_bilingual_voice_does_not_restart_when_reply_language_changes(
    tmp_path,
    monkeypatch,
):
    current = _install_packs(tmp_path, current_mode="neutts-nano")
    sidecar = current.parent / "multilingual"
    (sidecar / "voice-pack.json").write_text(
        json.dumps({
            "format_version": 1,
            "engine_mode": "moss-nano",
            "languages": ["de", "en"],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", current)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_OVERRIDE", False)
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")

    process = server.LocalVoiceProcess()
    events: list[tuple[str, str | None]] = []

    async def start(language="de"):
        process.process = SimpleNamespace(returncode=None)
        process.pack_dir = server._local_voice_pack_dir(language)
        process.mode = "neutts-nano"
        process.features = frozenset({"warm-language-cache"})
        process.warm_languages = {language}
        events.append(("start", language))

    async def warm_language(language):
        if language not in process.warm_languages:
            process.warm_languages.add(language)
            events.append(("warm", language))

    async def stop():
        events.append(("stop", process.pack_dir.name if process.pack_dir else None))
        process.process = None
        process.pack_dir = None

    monkeypatch.setattr(process, "_start", start)
    monkeypatch.setattr(process, "_stop_unlocked", stop)
    monkeypatch.setattr(process, "_warm_language_unlocked", warm_language)

    assert await process.warm("en") is True
    assert await process.warm("en") is True
    assert await process.warm("de") is True
    assert events == [("start", "en"), ("warm", "de")]


@pytest.mark.asyncio
async def test_resident_neutts_voice_warms_the_second_language_over_private_pipe(
    monkeypatch,
):
    class FakeStdin:
        def __init__(self):
            self.payload = b""

        def write(self, payload):
            self.payload = payload

        async def drain(self):
            return None

    stdin = FakeStdin()
    process = server.LocalVoiceProcess()
    process.process = SimpleNamespace(returncode=None, stdin=stdin)
    process.mode = "neutts-nano"
    process.features = frozenset({"warm-language-cache"})
    process.warm_languages = {"de"}

    async def read_message(timeout):
        assert timeout <= 45.0
        request = json.loads(stdin.payload)
        return {"type": "warm", "id": request["id"], "ok": True}

    monkeypatch.setattr(process, "_read_message", read_message)

    await process._warm_language_unlocked("en")

    request = json.loads(stdin.payload)
    assert request["type"] == "warm"
    assert request["language"] == "en"
    assert process.warm_languages == {"de", "en"}


def test_german_falls_back_to_english_when_the_pack_is_missing(tmp_path, monkeypatch):
    english = _install_packs(tmp_path, bilingual=False)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", english)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_OVERRIDE", False)
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "de-DE")
    assert server._local_voice_pack_dir() == english


def test_an_explicit_pack_path_is_never_redirected(packs, monkeypatch):
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_OVERRIDE", True)
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "multilingual")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "de-DE")
    assert server._local_voice_pack_dir() == packs


def test_a_manual_choice_overrides_the_language(packs, monkeypatch):
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "current")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "de-DE")
    assert server._local_voice_pack_dir().name == "current"


def test_saving_a_language_switches_the_pack_and_releases_the_engine(packs, monkeypatch):
    """Different weights mean the resident engine has to be restarted."""
    written: dict[str, str] = {}
    stopped: list[bool] = []

    async def stop():
        stopped.append(True)

    monkeypatch.setattr(server, "_write_env_key", lambda key, value: written.__setitem__(key, value))
    monkeypatch.setattr(server, "_reload_runtime_config", lambda: monkeypatch.setattr(
        server, "SPEECH_LANGUAGE", written.get("JARVIS_SPEECH_LANGUAGE", "auto")
    ))
    monkeypatch.setattr(server._local_voice_process, "stop", stop)
    monkeypatch.setattr(server._local_speech, "stop", stop)
    monkeypatch.setattr(server, "VOICE_PACK_CHOICE", "auto")
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "en-GB")

    client = TestClient(server.app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/settings/voice",
        headers=_auth_headers(),
        json={
            "provider": "local",
            "system_voice": "Auto",
            "system_rate": 165,
            "speech_language": "de-DE",
            "stt_provider": "local",
            "voice_pack": "auto",
        },
    )
    assert response.status_code == 200
    assert response.json()["success"] is True
    assert written["JARVIS_SPEECH_LANGUAGE"] == "de-DE"
    assert written["JARVIS_VOICE_PACK"] == "auto"
    assert stopped, "the engine must be released so the German pack can load"


def test_an_unknown_pack_name_is_rejected(monkeypatch):
    client = TestClient(server.app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/settings/voice",
        headers=_auth_headers(),
        json={
            "provider": "system",
            "system_voice": "Auto",
            "system_rate": 165,
            "speech_language": "auto",
            "stt_provider": "local",
            "voice_pack": "../../etc",
        },
    )
    assert response.status_code == 400


def test_wake_setting_is_persisted_by_the_backend(monkeypatch):
    written: dict[str, str] = {}

    def reload_runtime():
        monkeypatch.setattr(
            server,
            "WAKE_ENABLED",
            written.get("JARVIS_WAKE_ENABLED") == "1",
        )

    monkeypatch.setattr(
        server,
        "_write_env_key",
        lambda key, value: written.__setitem__(key, value),
    )
    monkeypatch.setattr(server, "_reload_runtime_config", reload_runtime)

    client = TestClient(server.app, base_url="http://127.0.0.1")
    response = client.post(
        "/api/settings/wake",
        headers=_auth_headers(),
        json={"enabled": True},
    )

    assert response.status_code == 200
    assert response.json() == {"success": True, "enabled": True}
    assert written["JARVIS_WAKE_ENABLED"] == "1"


def test_neutts_windows_pack_requires_a_windows_pronunciation_dll(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "win32")
    files = server._local_voice_neutts_model_files()

    assert "espeak/espeak-ng.dll" in files
    assert not any(filename.endswith(".dylib") for filename in files)


def test_neutts_mac_pack_keeps_the_native_dylib(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    files = server._local_voice_neutts_model_files()

    assert "espeak/libespeak-ng.1.52.0.1.dylib" in files
    assert not any(filename.endswith(".dll") for filename in files)
