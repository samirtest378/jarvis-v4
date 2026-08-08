"""Cloud speech recognition: provider order, fallbacks, and idle release."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import server


WAV = b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * 40


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload or {}

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class _FakeClient:
    """Minimal stand-in for httpx.AsyncClient that records the models tried."""

    def __init__(self, responses: list[_FakeResponse]) -> None:
        self._responses = responses
        self.models: list[str] = []
        self.payloads: list[dict] = []

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def post(self, _url: str, headers=None, files=None, data=None) -> _FakeResponse:
        self.models.append((data or {}).get("model", ""))
        self.payloads.append(dict(data or {}))
        return self._responses.pop(0)


def _configure(monkeypatch, *, provider="auto", openai="", fish="", local=False) -> None:
    monkeypatch.setattr(server, "STT_PROVIDER", provider)
    monkeypatch.setattr(server, "OPENAI_API_KEY", openai)
    monkeypatch.setattr(server, "FISH_API_KEY", fish)
    monkeypatch.setattr(server._local_speech, "status", lambda: {"available": local})


def test_auto_prefers_cloud_engines_over_the_local_model(monkeypatch):
    _configure(monkeypatch, openai="sk-test", fish="fish-test", local=True)
    assert server._stt_provider_chain() == ["openai", "fish", "local"]


def test_cloud_first_session_keeps_the_local_fallback_warm(monkeypatch):
    _configure(monkeypatch, openai="sk-test", local=True)
    prepared = False
    released = False

    async def prepare():
        nonlocal prepared
        prepared = True

    def release():
        nonlocal released
        released = True

    monkeypatch.setattr(server._local_speech, "prepare", prepare)
    monkeypatch.setattr(server._local_speech, "release", release)

    result = asyncio.run(server.api_speech_session(server.SpeechSessionUpdate(enabled=True)))

    assert result["success"] is True
    assert prepared is True
    assert released is False


def test_local_first_session_preloads_recognition(monkeypatch):
    _configure(monkeypatch, provider="local", local=True)
    prepared = False

    async def prepare():
        nonlocal prepared
        prepared = True

    monkeypatch.setattr(server._local_speech, "prepare", prepare)

    result = asyncio.run(server.api_speech_session(server.SpeechSessionUpdate(enabled=True)))

    assert result["success"] is True
    assert prepared is True


def test_missing_keys_leave_only_the_local_engine(monkeypatch):
    _configure(monkeypatch, local=True)
    assert server._stt_provider_chain() == ["local"]


def test_switching_recognition_off_disables_every_engine(monkeypatch):
    _configure(monkeypatch, provider="off", openai="sk-test", local=True)
    assert server._stt_provider_chain() == []
    with pytest.raises(RuntimeError, match="switched off"):
        asyncio.run(server.transcribe_speech(WAV, "de-DE"))


def test_an_explicit_choice_never_switches_provider_behind_the_users_back(monkeypatch):
    _configure(monkeypatch, provider="fish", openai="sk-test", fish="fish-test", local=True)
    assert server._stt_provider_chain() == ["fish"]


def test_recognition_falls_through_to_the_next_engine(monkeypatch):
    _configure(monkeypatch, openai="sk-test", fish="fish-test")

    async def failing(_audio, _language):
        raise RuntimeError("cloud unreachable")

    async def working(_audio, _language):
        return "es funktioniert"

    monkeypatch.setattr(server, "_transcribe_openai", failing)
    monkeypatch.setattr(server, "_transcribe_fish", working)

    assert asyncio.run(server.transcribe_speech(WAV, "de-DE")) == ("es funktioniert", "fish")


def test_recognition_reports_failure_once_every_engine_is_exhausted(monkeypatch):
    _configure(monkeypatch, openai="sk-test")

    async def failing(_audio, _language):
        raise RuntimeError("cloud unreachable")

    monkeypatch.setattr(server, "_transcribe_openai", failing)
    with pytest.raises(RuntimeError, match="Speech recognition failed"):
        asyncio.run(server.transcribe_speech(WAV, "de-DE"))


@pytest.mark.parametrize(
    ("audio", "language", "message"),
    [
        (b"not audio", "de-DE", "PCM WAV"),
        (WAV, "fr-FR", "Unsupported speech language"),
        (b"RIFF" + b"\x00" * 4 + b"WAVE" + b"\x00" * (9 * 1024 * 1024), "de-DE", "too large"),
    ],
    ids=("not-wav", "unsupported-language", "oversized-wav"),
)
def test_invalid_audio_is_rejected_before_any_engine_runs(monkeypatch, audio, language, message):
    _configure(monkeypatch, openai="sk-test")

    async def unreachable(_audio, _language):  # pragma: no cover - must not run
        raise AssertionError("validation must reject the request first")

    monkeypatch.setattr(server, "_transcribe_openai", unreachable)
    with pytest.raises(ValueError, match=message):
        asyncio.run(server.transcribe_speech(audio, language))


def test_automatic_language_sends_no_hint_so_the_engine_detects_it(monkeypatch):
    """German one sentence, English the next — without changing a setting."""
    client = _FakeClient([_FakeResponse(200, {"text": "hallo"})])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr(server, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(server, "STT_MODEL", "whisper-1")
    monkeypatch.setattr(server, "_stt_model_fallback", "")

    asyncio.run(server._transcribe_openai(WAV, None))
    assert "language" not in client.payloads[0]


def test_every_transcription_is_primed_with_the_words_jarvis_hears_most(monkeypatch):
    """Without this, "Hey JARVIS" comes back as "Hey Travis" and friends."""
    client = _FakeClient([_FakeResponse(200, {"text": "hallo"})])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr(server, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(server, "STT_MODEL", "whisper-1")
    monkeypatch.setattr(server, "_stt_model_fallback", "")

    asyncio.run(server._transcribe_openai(WAV, None))
    hint = client.payloads[0]["prompt"]
    assert "JARVIS" in hint
    assert "Kalender" in hint and "Gmail" in hint
    assert len(hint) < 120


def test_an_explicit_language_is_still_passed_through(monkeypatch):
    client = _FakeClient([_FakeResponse(200, {"text": "hallo"})])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr(server, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(server, "STT_MODEL", "whisper-1")
    monkeypatch.setattr(server, "_stt_model_fallback", "")

    asyncio.run(server._transcribe_openai(WAV, "de"))
    assert client.payloads[0]["language"] == "de"


@pytest.mark.parametrize("language", ["auto", "de-DE", "en-US", "en-GB"])
def test_supported_languages_include_automatic(monkeypatch, language):
    _configure(monkeypatch, openai="sk-test")

    async def transcribe(_audio, _language):
        return "erkannt"

    monkeypatch.setattr(server, "_transcribe_openai", transcribe)
    text, _engine = asyncio.run(server.transcribe_speech(WAV, language))
    assert text == "erkannt"


def test_a_rejected_model_name_falls_back_to_whisper_1(monkeypatch):
    client = _FakeClient([_FakeResponse(404), _FakeResponse(200, {"text": "hallo"})])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr(server, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(server, "STT_MODEL", "gpt-4o-mini-transcribe")
    monkeypatch.setattr(server, "_stt_model_fallback", "")

    assert asyncio.run(server._transcribe_openai(WAV, "de")) == "hallo"
    assert client.models == ["gpt-4o-mini-transcribe", "whisper-1"]
    # The working name is remembered so later dictations skip the failed probe.
    assert server._stt_model_fallback == "whisper-1"


def test_an_authentication_error_is_not_retried_with_another_model(monkeypatch):
    client = _FakeClient([_FakeResponse(401)])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    monkeypatch.setattr(server, "OPENAI_API_KEY", "sk-test")
    monkeypatch.setattr(server, "STT_MODEL", "gpt-4o-mini-transcribe")

    with pytest.raises(RuntimeError, match="401"):
        asyncio.run(server._transcribe_openai(WAV, "de"))
    assert client.models == ["gpt-4o-mini-transcribe"]


def test_the_local_engine_releases_its_model_when_idle():
    service = server.LocalSpeechRecognition()
    assert service.IDLE_TIMEOUT > 0
    # Nothing was started, so the watcher must terminate instead of spinning.
    service._last_use = 0.0
    asyncio.run(asyncio.wait_for(service._release_when_idle(), timeout=20.0))
    assert service.running is False


@pytest.mark.parametrize(
    ("text", "unexpected"),
    [
        ("Hey JARVIS, öffne YouTube.", False),
        ("Hey JARVIS, open YouTube.", False),
        ("אל גראביס, אף ניותיות", True),
        ("", False),
    ],
)
def test_bilingual_local_recognition_rejects_unexpected_scripts(text, unexpected):
    assert server._has_unexpected_speech_script(text) is unexpected


@pytest.mark.parametrize(
    ("language", "supported"),
    [
        ("German", True),
        ("de", True),
        ("English", True),
        ("en-GB", True),
        ("Polish", False),
        ("French", False),
        ("", False),
    ],
)
def test_local_recognition_accepts_only_german_and_english(language, supported):
    assert server._is_supported_recognition_language(language) is supported


def test_local_recognition_confidence_is_length_weighted():
    payload = {
        "segments": [
            {"text": "kurz", "avg_logprob": -0.8},
            {"text": "dieser Abschnitt ist deutlich länger", "avg_logprob": -0.1},
        ]
    }

    confidence = server._transcription_confidence(payload)

    assert confidence is not None
    assert -0.25 < confidence < -0.1
    assert server._transcription_confidence({"text": "ohne Segmente"}) is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"text": "Hallo JARVIS.", "language": "German"}, "Hallo JARVIS."),
        ({"text": "Hello JARVIS.", "language": "English"}, "Hello JARVIS."),
    ],
)
def test_automatic_local_recognition_is_strictly_bilingual(monkeypatch, payload, expected):
    client = _FakeClient([_FakeResponse(200, payload)])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    service = server.LocalSpeechRecognition()
    service.process = SimpleNamespace(returncode=None)
    service.port = 12345

    assert asyncio.run(service.transcribe(WAV, "auto")) == expected
    assert client.payloads[0]["response_format"] == "verbose_json"
    assert client.payloads[0]["no_language_probabilities"] == "true"
    assert client.payloads[0]["vad"] == "true"
    assert client.payloads[0]["vad_speech_pad_ms"] == "250"
    assert "JARVIS" in client.payloads[0]["prompt"]


def test_unsupported_auto_label_recovers_german_or_english(monkeypatch):
    client = _FakeClient([
        _FakeResponse(200, {
            "text": "Open mijn kalender.",
            "language": "Dutch",
            "segments": [{"text": "Open mijn kalender.", "avg_logprob": -0.18}],
        }),
        _FakeResponse(200, {
            "text": "Öffne meinen Kalender.",
            "language": "German",
            "segments": [{"text": "Öffne meinen Kalender.", "avg_logprob": -0.09}],
        }),
        _FakeResponse(200, {
            "text": "Open my calendar.",
            "language": "English",
            "segments": [{"text": "Open my calendar.", "avg_logprob": -0.52}],
        }),
    ])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    service = server.LocalSpeechRecognition()
    service.process = SimpleNamespace(returncode=None)
    service.port = 12345

    assert asyncio.run(service.transcribe(WAV, "auto")) == "Öffne meinen Kalender."
    assert [payload["language"] for payload in client.payloads] == ["auto", "de", "en"]


def test_weak_auto_decode_retries_only_the_other_conversation_language(monkeypatch):
    client = _FakeClient([
        _FakeResponse(200, {
            "text": "Open my calendar.",
            "language": "English",
            "segments": [{"text": "Open my calendar.", "avg_logprob": -0.82}],
        }),
        _FakeResponse(200, {
            "text": "Öffne meinen Kalender.",
            "language": "German",
            "segments": [{"text": "Öffne meinen Kalender.", "avg_logprob": -0.12}],
        }),
    ])
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **_kwargs: client)
    service = server.LocalSpeechRecognition()
    service.process = SimpleNamespace(returncode=None)
    service.port = 12345

    assert asyncio.run(service.transcribe(WAV, "auto")) == "Öffne meinen Kalender."
    assert [payload["language"] for payload in client.payloads] == ["auto", "de"]
    assert all(payload["beam_size"] == "3" for payload in client.payloads)


def test_every_recognition_provider_normalizes_common_jarvis_spellings(monkeypatch):
    _configure(monkeypatch, openai="sk-test")

    async def transcribe(_audio, _language):
        return "Hey Jervis, öffne YouTube."

    monkeypatch.setattr(server, "_transcribe_openai", transcribe)
    text, _engine = asyncio.run(server.transcribe_speech(WAV, "auto"))
    assert text == "Hey JARVIS, öffne YouTube."


@pytest.mark.parametrize(
    ("text", "german"),
    [
        ("Ich öffne jetzt den Kalender für Sie.", True),
        ("Guten Abend. Alle Systeme sind bereit.", True),
        ("Sie haben heute drei Termine.", True),
        ("Opening YouTube now, sir.", False),
        ("You have three meetings today.", False),
        ("Checking your calendar.", False),
    ],
)
def test_german_is_recognised_before_choosing_a_voice(text, german):
    assert server.spoken_text_is_german(text) is german


def test_german_never_reaches_the_english_only_video_voice(monkeypatch):
    """Measured: it turns German into gibberish, so it must not be used for it."""
    spoken: list[str] = []

    async def video_voice(text):
        spoken.append(text)
        return b"RIFF-video"

    async def system_voice(_text):
        return b"RIFF-system"

    monkeypatch.setattr(server, "TTS_PROVIDER", "local")
    monkeypatch.setattr(server, "OPENAI_API_KEY", "")
    monkeypatch.setattr(server, "FISH_API_KEY", "")
    monkeypatch.setattr(server, "_local_voice_paths", lambda: True)
    monkeypatch.setattr(server, "_synthesize_local_video_voice", video_voice)
    monkeypatch.setattr(server, "_synthesize_system_speech", system_voice)
    monkeypatch.setattr(server, "_session_tokens", {"tts_calls": 0})
    monkeypatch.setattr(server, "_append_usage_entry", lambda *_args: None)

    assert asyncio.run(server.synthesize_speech("Sie haben heute drei Termine.")) == b"RIFF-system"
    assert spoken == [], "German must never be handed to the English-only voice"

    # English still gets the JARVIS voice the user chose.
    assert asyncio.run(server.synthesize_speech("You have three meetings today.")) == b"RIFF-video"
    assert spoken == ["You have three meetings today."]
