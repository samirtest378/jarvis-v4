import os
import json
import sys
from pathlib import Path

import pytest

import server


def _isolated_env(monkeypatch, tmp_path: Path) -> Path:
    target = tmp_path / "config" / ".env"
    monkeypatch.setattr(server, "ENV_FILE", target)
    monkeypatch.setattr(server, "ENV_EXAMPLE_FILE", tmp_path / "missing.example")
    return target


def test_env_writer_uses_private_file_permissions(monkeypatch, tmp_path):
    target = _isolated_env(monkeypatch, tmp_path)
    monkeypatch.delenv("TEST_SETTING", raising=False)

    server._write_env_key("TEST_SETTING", "safe-value")

    assert target.read_text(encoding="utf-8") == "TEST_SETTING=safe-value\n"
    assert os.environ["TEST_SETTING"] == "safe-value"
    if os.name == "posix":
        assert target.stat().st_mode & 0o077 == 0


def test_env_writer_rejects_line_injection(monkeypatch, tmp_path):
    target = _isolated_env(monkeypatch, tmp_path)

    with pytest.raises(ValueError, match="line breaks"):
        server._write_env_key("ANTHROPIC_API_KEY", "valid\nINJECTED=value")

    assert not target.exists()


def test_provider_key_aliases_and_example_placeholders(monkeypatch):
    monkeypatch.setenv("MOONSHOT_API_KEY", "your-moonshot-api-key-here")
    monkeypatch.setenv("KIMI_API_KEY", "Bearer kimi-test")
    assert server._provider_api_key("kimi") == "kimi-test"

    monkeypatch.setenv("KIMI_API_KEY", "your-kimi-api-key-here")
    assert server._provider_api_key("kimi") == ""


@pytest.mark.parametrize(
    ("provider", "canonical", "alias"),
    [
        ("kimi", "MOONSHOT_API_KEY", "KIMI_API_KEY"),
        ("qwen", "DASHSCOPE_API_KEY", "QWEN_API_KEY"),
        ("gemini", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
        ("grok", "XAI_API_KEY", "GROK_API_KEY"),
    ],
)
def test_all_provider_aliases_reach_runtime(monkeypatch, provider, canonical, alias):
    monkeypatch.delenv(canonical, raising=False)
    monkeypatch.setenv(alias, f"export {alias}='alias-secret=='")

    assert server._provider_api_key(provider) == "alias-secret=="


def test_openai_and_custom_keys_are_kept_separate(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("OPENAI_COMPATIBLE_API_KEY", "custom-secret")

    assert server._provider_api_key("openai") == "openai-secret"
    assert server._provider_api_key("custom") == "custom-secret"


@pytest.mark.asyncio
async def test_browser_key_save_normalizes_assignment_before_persisting(monkeypatch, tmp_path):
    target = _isolated_env(monkeypatch, tmp_path)
    monkeypatch.setattr(server, "_reload_runtime_config", lambda: None)

    response = await server.api_settings_keys(server.KeyUpdate(
        key_name="ANTHROPIC_API_KEY",
        key_value="Authorization: Bearer example-secret==",
    ))

    assert response == {"success": True, "applied": True}
    assert target.read_text(encoding="utf-8") == "ANTHROPIC_API_KEY=example-secret==\n"


@pytest.mark.asyncio
async def test_browser_key_save_rejects_placeholder(monkeypatch, tmp_path):
    target = _isolated_env(monkeypatch, tmp_path)

    response = await server.api_settings_keys(server.KeyUpdate(
        key_name="GEMINI_API_KEY",
        key_value="your-gemini-api-key-here",
    ))

    assert response.status_code == 400
    assert not target.exists()


def test_reload_normalizes_fish_key_from_environment(monkeypatch):
    monkeypatch.setenv("FISH_API_KEY", "Authorization: Bearer fish-secret==")
    monkeypatch.setattr(server, "_create_configured_llm_client", lambda: None)

    server._reload_runtime_config()

    assert server.FISH_API_KEY == "fish-secret=="


@pytest.mark.asyncio
async def test_fish_test_normalizes_pasted_bearer_header(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200
        content = b"ID3-fish-audio"
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, *, headers, json):
            captured.update(headers=headers, json=json)
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    result = await server.api_test_fish(server.FishTest(
        key_value="FISH_API_KEY='fish-secret=='",
        voice_id="voice-reference",
    ))

    assert result["valid"] is True
    assert result["voice_id"] == "voice-reference"
    assert result["audio"] == "SUQzLWZpc2gtYXVkaW8="
    assert captured["headers"]["Authorization"] == "Bearer fish-secret=="
    assert captured["headers"]["model"] == "s2-pro"
    assert captured["json"]["reference_id"] == "voice-reference"
    assert captured["json"]["format"] == "mp3"


@pytest.mark.asyncio
async def test_fish_connection_check_does_not_return_audio(monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b"ID3-fish-audio"
        headers = {"content-type": "audio/mpeg"}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, _url, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)

    result = await server.api_test_fish(server.FishTest(
        key_value="fish-secret",
        voice_id="voice-reference",
        include_audio=False,
    ))

    assert result["valid"] is True
    assert "audio" not in result
    assert "mime" not in result


@pytest.mark.asyncio
async def test_fish_test_requires_an_explicit_licensed_voice_id(monkeypatch):
    monkeypatch.setattr(server, "FISH_VOICE_ID", "")

    class FailIfCalled:
        def __init__(self, **_kwargs):
            raise AssertionError("Fish must not be called without an explicit voice ID")

    monkeypatch.setattr(server.httpx, "AsyncClient", FailIfCalled)

    result = await server.api_test_fish(server.FishTest(
        key_value="fish-secret",
        voice_id="",
    ))

    assert result == {
        "valid": False,
        "error": "Enter a Fish Voice ID that you are licensed to use.",
    }


def test_intent_fallback_still_routes_without_llm():
    assert server._classify_intent_fallback("search for FastAPI docs")["action"] == "browse"
    assert server._classify_intent_fallback("build me a dashboard")["action"] == "build"
    assert server._classify_intent_fallback("good morning")["action"] == "chat"


@pytest.mark.asyncio
async def test_local_model_discovery_lists_only_model_ids(monkeypatch):
    class FakeResponse:
        is_error = False
        status_code = 200

        def json(self):
            return {"data": [{"id": "qwen3.5:9b"}, {"id": "qwen3.5:27b"}, {"not_id": "ignored"}]}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url):
            assert url == "http://127.0.0.1:11434/v1/models"
            return FakeResponse()

    monkeypatch.setattr(server.httpx, "AsyncClient", FakeClient)
    result = await server.api_local_models("http://127.0.0.1:11434/v1")

    assert result == {"available": True, "models": ["qwen3.5:27b", "qwen3.5:9b"]}


@pytest.mark.asyncio
async def test_local_model_discovery_rejects_remote_hosts():
    result = await server.api_local_models("https://example.com/v1")
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_local_model_install_rejects_unsafe_model_name():
    result = await server.api_install_local_model(server.LocalModelInstallRequest(model="../../secret"))
    assert result.status_code == 400


@pytest.mark.asyncio
async def test_local_model_install_explains_when_ollama_is_missing(monkeypatch):
    monkeypatch.setattr(server, "_resolve_ollama_executable", lambda: None)
    result = await server.api_install_local_model(server.LocalModelInstallRequest(model="qwen3.5:9b"))
    assert result.status_code == 409


def test_ollama_executable_accepts_an_explicit_installed_runtime(monkeypatch, tmp_path):
    executable = tmp_path / ("ollama.exe" if server.sys.platform == "win32" else "ollama")
    executable.write_bytes(b"runtime")
    executable.chmod(0o700)
    monkeypatch.setenv("JARVIS_OLLAMA_EXECUTABLE", str(executable))

    assert server._resolve_ollama_executable() == str(executable)


def test_ollama_child_environment_never_inherits_cloud_secrets(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-anthropic")
    monkeypatch.setenv("FISH_API_KEY", "secret-fish")
    monkeypatch.setenv("PATH", "/safe/bin")

    environment = server._ollama_child_environment("http://127.0.0.1:11434/v1")

    assert environment["PATH"] == "/safe/bin"
    assert environment["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert "ANTHROPIC_API_KEY" not in environment
    assert "FISH_API_KEY" not in environment


@pytest.mark.asyncio
async def test_local_readiness_requires_the_selected_model(monkeypatch):
    async def snapshot(_base_url):
        return {"available": True, "models": ["qwen3.5:4b"]}

    monkeypatch.setattr(server, "_fetch_local_models", snapshot)
    monkeypatch.setattr(server, "_resolve_ollama_executable", lambda: "/safe/ollama")

    missing = await server._local_llm_readiness("http://127.0.0.1:11434/v1", "qwen3.5:9b")
    ready = await server._local_llm_readiness("http://127.0.0.1:11434/v1", "qwen3.5:4b")

    assert missing["ready"] is False
    assert missing["service_available"] is True
    assert missing["installed_models"] == ["qwen3.5:4b"]
    assert ready["ready"] is True


@pytest.mark.asyncio
async def test_start_local_runtime_explains_when_ollama_is_not_installed(monkeypatch):
    async def unavailable(_base_url):
        return {"available": False, "models": [], "error": "stopped"}

    monkeypatch.setattr(server, "_fetch_local_models", unavailable)
    monkeypatch.setattr(server, "_resolve_ollama_executable", lambda: None)

    result = await server._start_managed_ollama()

    assert result["success"] is False
    assert "not installed" in result["error"]


@pytest.mark.asyncio
async def test_start_local_runtime_launches_a_sanitized_managed_service(monkeypatch):
    checks = 0
    captured = {}

    async def snapshot(_base_url):
        nonlocal checks
        checks += 1
        return {"available": checks > 1, "models": []}

    class FakeProcess:
        returncode = None

    async def create_process(*command, **options):
        captured.update(command=command, options=options)
        return FakeProcess()

    async def no_wait(_seconds):
        return None

    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-ollama")
    monkeypatch.setattr(server, "_fetch_local_models", snapshot)
    monkeypatch.setattr(server, "_resolve_ollama_executable", lambda: "/safe/ollama")
    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", create_process)
    monkeypatch.setattr(server.asyncio, "sleep", no_wait)
    monkeypatch.setattr(server, "_managed_ollama_process", None)

    result = await server._start_managed_ollama()

    assert result == {"success": True, "started": True, "already_running": False}
    assert captured["command"] == ("/safe/ollama", "serve")
    assert "ANTHROPIC_API_KEY" not in captured["options"]["env"]
    monkeypatch.setattr(server, "_managed_ollama_process", None)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (401, "expired, or revoked"),
        (402, "billing"),
        (403, "lacks access"),
        (404, "model or endpoint"),
        (429, "rate limit"),
        (503, "temporarily unavailable"),
    ],
)
def test_llm_errors_are_actionable_and_do_not_echo_secrets(status, expected):
    class ProviderError(RuntimeError):
        status_code = status

    message = server._friendly_llm_error("anthropic", ProviderError("sensitive-provider-detail"))

    assert expected in message
    assert "sensitive-provider-detail" not in message


@pytest.mark.parametrize(
    ("provider", "expected"),
    [
        ("openai", "separate from a ChatGPT subscription"),
        ("kimi", "platform.kimi.ai"),
        ("qwen", "region-specific"),
    ],
)
def test_provider_specific_auth_errors_explain_the_common_setup_mismatch(provider, expected):
    class ProviderError(RuntimeError):
        status_code = 401

    assert expected in server._friendly_llm_error(provider, ProviderError("secret"))


def test_chat_llm_error_replaces_generic_reply_without_echoing_secret():
    class ProviderError(RuntimeError):
        status_code = 401

    message = server._chat_llm_error("anthropic", ProviderError("secret-provider-payload"))

    assert "Anthropic" in message
    assert "ANTHROPIC_API_KEY" in message
    assert "Test provider" in message
    assert "secret-provider-payload" not in message


@pytest.mark.asyncio
async def test_generate_response_surfaces_authentication_fix_in_chat(monkeypatch):
    class ProviderError(RuntimeError):
        status_code = 401

    class FakeMessages:
        async def create(self, **_kwargs):
            raise ProviderError("secret-provider-payload")

    class FakeClient:
        messages = FakeMessages()

    class FakeTaskManager:
        @staticmethod
        def get_active_tasks_summary():
            return "No active tasks."

    monkeypatch.setattr(server, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(server, "build_memory_context", lambda _text: "")
    monkeypatch.setattr(server, "get_lookup_status", lambda: "")

    message = await server.generate_response(
        "How are you?",
        FakeClient(),
        FakeTaskManager(),
        [],
        [{"role": "user", "content": "How are you?"}],
    )

    assert "ANTHROPIC_API_KEY" in message
    assert "invalid, expired, or revoked" in message
    assert "secret-provider-payload" not in message
    assert "trouble connecting to my language systems" not in message


@pytest.mark.asyncio
async def test_text_is_delivered_before_slow_voice_finishes(monkeypatch):
    synthesis_started = __import__("asyncio").Event()
    release_synthesis = __import__("asyncio").Event()

    async def slow_synthesis(_text):
        synthesis_started.set()
        await release_synthesis.wait()
        return b"voice-bytes"

    class FakeSocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    monkeypatch.setattr(server, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(server, "synthesize_speech", slow_synthesis)
    socket = FakeSocket()
    task = __import__("asyncio").create_task(
        server.send_response_with_deferred_voice(socket, "Systems ready, sir.")
    )

    await synthesis_started.wait()
    assert socket.messages == [{
        "type": "text",
        "text": "Systems ready, sir.",
        "speak": False,
        "voice_pending": True,
    }]

    release_synthesis.set()
    await task
    assert socket.messages[1] == {"type": "status", "state": "speaking"}
    assert socket.messages[2]["type"] == "audio"
    assert socket.messages[2]["text"] == "Systems ready, sir."


@pytest.mark.asyncio
async def test_long_voice_answers_start_with_first_sentence(monkeypatch):
    calls = []

    async def synthesize(text):
        calls.append(text)
        return f"RIFF-{len(calls)}".encode()

    class FakeSocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    monkeypatch.setattr(server, "TTS_PROVIDER", "local")
    monkeypatch.setattr(server, "synthesize_speech", synthesize)
    socket = FakeSocket()
    answer = (
        "Der erste Abschnitt erklärt die wichtigste Änderung ausführlich und verständlich. "
        "Der zweite Abschnitt enthält zusätzliche Einzelheiten, damit die gesamte Antwort "
        "lang genug für die früh startende, satzweise Sprachausgabe ist. "
        "Zum Schluss folgt eine kurze Zusammenfassung."
    )

    await server.send_response_with_deferred_voice(socket, answer)

    audio = [message for message in socket.messages if message["type"] == "audio"]
    assert len(calls) >= 2
    assert len(audio) == len(calls)
    assert audio[0]["stream_index"] == 0
    assert audio[0]["stream_final"] is False
    assert audio[-1]["stream_final"] is True


@pytest.mark.asyncio
async def test_system_voice_starts_in_renderer_without_wav_generation(monkeypatch):
    async def must_not_render_wav(_text):
        raise AssertionError("native browser speech must start without rendering a WAV")

    class FakeSocket:
        def __init__(self):
            self.messages = []

        async def send_json(self, message):
            self.messages.append(message)

    monkeypatch.setattr(server, "TTS_PROVIDER", "system")
    monkeypatch.setattr(server, "synthesize_speech", must_not_render_wav)
    socket = FakeSocket()

    await server.send_response_with_deferred_voice(socket, "Systems ready, sir.")

    assert socket.messages == [
        {
            "type": "text",
            "text": "Systems ready, sir.",
            "speak": False,
            "voice_pending": True,
        },
        {
            "type": "audio",
            "data": "",
            "text": "Systems ready sir",
            "speak": True,
        },
    ]


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, "Voice ID"),
        (401, "rejected the API key"),
        (402, "credits"),
        (403, "permission"),
        (404, "not found"),
        (429, "rate-limiting"),
        (503, "temporarily unavailable"),
    ],
)
def test_fish_errors_are_actionable_and_do_not_echo_payload(status, expected):
    message = server._friendly_fish_error(status, RuntimeError("secret-fish-payload"))

    assert expected in message
    assert "secret-fish-payload" not in message


def test_tts_status_auto_prefers_reference_voice_when_configured(monkeypatch):
    monkeypatch.setattr(server, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(server, "OPENAI_API_KEY", "")
    monkeypatch.setattr(server, "FISH_API_KEY", "configured")
    monkeypatch.setattr(server, "FISH_VOICE_ID", "reference-id")
    monkeypatch.setattr(server, "_system_tts_engine", lambda _language=None: ("macos-say", "Daniel"))

    status = server._tts_status()

    assert status["active_provider"] == "fish"
    assert status["reference_voice_id"] == "reference-id"
    assert status["system_available"] is True


def test_tts_status_reports_text_only_when_voice_is_disabled(monkeypatch):
    monkeypatch.setattr(server, "TTS_PROVIDER", "off")
    monkeypatch.setattr(server, "_system_tts_engine", lambda _language=None: ("macos-say", "Daniel"))

    status = server._tts_status()

    assert status["configured_provider"] == "off"
    assert status["active_provider"] == "unavailable"


@pytest.mark.asyncio
async def test_tts_auto_falls_back_to_local_voice(monkeypatch):
    calls = []

    async def failed_reference(_text):
        calls.append("fish")
        return None

    async def local_voice(_text):
        calls.append("system")
        return b"FORM-local-audio"

    monkeypatch.setattr(server, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(server, "OPENAI_API_KEY", "")
    monkeypatch.setattr(server, "FISH_API_KEY", "configured")
    monkeypatch.setattr(server, "_synthesize_fish_speech", failed_reference)
    monkeypatch.setattr(server, "_synthesize_system_speech", local_voice)
    monkeypatch.setattr(server, "_session_tokens", {"tts_calls": 0})
    monkeypatch.setattr(server, "_append_usage_entry", lambda *_args: None)

    audio = await server.synthesize_speech("Good morning, sir.")

    assert audio == b"FORM-local-audio"
    assert calls == ["fish", "system"]
    assert server._last_tts_provider == "system"
    assert server._session_tokens["tts_calls"] == 1


def _fake_voice_pack(tmp_path: Path, mode: str = "turbo") -> Path:
    pack = tmp_path / "voice-pack"
    engine = pack / "bin" / ("jarvis-voice-engine.exe" if sys.platform == "win32" else "jarvis-voice-engine")
    python_engine = pack / "bin" / "jarvis-voice-engine.py"
    engine.parent.mkdir(parents=True)
    (pack / "models").mkdir()
    engine_source = (
        f"#!{sys.executable}\n"
        "import base64,json,sys\n"
        "print(json.dumps({'type':'ready','protocol':1,'device':'test','sample_rate':24000}),flush=True)\n"
        "for line in sys.stdin:\n"
        " r=json.loads(line); print(json.dumps({'type':'audio','id':r['id'],'audio':base64.b64encode(b'RIFF-test-audio').decode()}),flush=True)\n"
    )
    engine.write_text(engine_source, encoding="utf-8")
    python_engine.write_text(engine_source, encoding="utf-8")
    engine.chmod(0o755)
    python_engine.chmod(0o755)
    manifest = {"format_version": 1, "name": "Test Voice", "version": "1"}
    if mode == "multilingual":
        manifest.update({"engine_mode": "multilingual", "languages": ["de", "en"]})
    (pack / "voice-pack.json").write_text(json.dumps(manifest))
    (pack / "profile.pt").write_bytes(b"profile")
    model_files = (
        server._LOCAL_VOICE_MULTILINGUAL_MODEL_FILES
        if mode == "multilingual"
        else server._LOCAL_VOICE_REQUIRED_MODEL_FILES
    )
    for filename in model_files:
        (pack / "models" / filename).write_bytes(b"model")
    return pack


@pytest.mark.asyncio
async def test_local_voice_process_uses_private_json_pipe(monkeypatch, tmp_path):
    pack = _fake_voice_pack(tmp_path)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", pack)
    native_paths = server._local_voice_paths()
    assert native_paths is not None
    _native_engine, models, profile = native_paths
    python_engine = pack / "bin" / "jarvis-voice-engine.py"
    monkeypatch.setattr(
        server,
        "_local_voice_paths",
        lambda _language=None: (python_engine, models, profile),
    )
    process = server.LocalVoiceProcess()

    audio = await process.synthesize("Systems ready, sir.")

    assert audio == b"RIFF-test-audio"
    assert process.running is True
    assert process.device == "test"
    await process.stop()
    assert process.running is False


def test_windows_voice_process_explicitly_uses_the_cpu_engine(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "win32")
    assert server.LocalVoiceProcess._device() == "cpu"


def test_macos_voice_process_keeps_the_native_auto_acceleration(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    assert server.LocalVoiceProcess._device() == "auto"


@pytest.mark.asyncio
async def test_multilingual_profile_speaks_german_through_local_voice(monkeypatch, tmp_path):
    pack = _fake_voice_pack(tmp_path, mode="multilingual")
    spoken = []

    async def local_voice(text):
        spoken.append(text)
        return b"RIFF-german-voice"

    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", pack)
    monkeypatch.setattr(server, "TTS_PROVIDER", "local")
    monkeypatch.setattr(server, "_synthesize_local_video_voice", local_voice)
    monkeypatch.setattr(server, "_session_tokens", {"tts_calls": 0})
    monkeypatch.setattr(server, "_append_usage_entry", lambda *_args: None)

    audio = await server.synthesize_speech("Ich öffne jetzt den Kalender für Sie.")

    assert audio == b"RIFF-german-voice"
    assert spoken == ["Ich öffne jetzt den Kalender für Sie."]
    assert server._local_voice_languages() == frozenset({"de", "en"})
    assert server._last_tts_provider == "local"


def test_tts_status_auto_prefers_configured_fish_over_offline_video_voice(monkeypatch, tmp_path):
    pack = _fake_voice_pack(tmp_path)
    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", pack)
    monkeypatch.setattr(server, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(server, "OPENAI_API_KEY", "")
    monkeypatch.setattr(server, "FISH_API_KEY", "configured")
    monkeypatch.setattr(server, "FISH_VOICE_ID", "reference-id")

    status = server._tts_status()

    assert status["active_provider"] == "fish"
    assert status["local_ready"] is True
    assert status["local_pack_name"] == "Test Voice"


@pytest.mark.asyncio
async def test_macos_system_voice_is_normalized_to_wav(monkeypatch):
    """Electron receives PCM WAV, not the AIFF emitted by macOS ``say``."""
    if not Path("/usr/bin/afconvert").exists():
        pytest.skip("macOS afconvert is unavailable")

    calls = []

    async def fake_command(command, output_path):
        calls.append(command)
        payload = b"FORM-aiff" if output_path.suffix == ".aiff" else b"RIFF-wav"
        output_path.write_bytes(payload)
        return payload

    monkeypatch.setattr(server, "_system_tts_engine", lambda _language=None: ("macos-say", "Daniel"))
    monkeypatch.setattr(server, "_run_tts_command", fake_command)

    audio = await server._synthesize_system_speech("Systems ready, sir.")

    assert audio == b"RIFF-wav"
    assert len(calls) == 2
    assert calls[0][0:2] == ["/usr/bin/say", "-v"]
    assert calls[1][0:4] == ["/usr/bin/afconvert", "-f", "WAVE", "-d"]


def test_automatic_macos_voice_follows_speech_language():
    names = frozenset({"Anna", "Daniel", "Samantha"})

    assert server._select_macos_system_voice(names, "Auto", "de-DE") == "Anna"
    assert server._select_macos_system_voice(names, "Auto", "en-GB") == "Daniel"
    assert server._select_macos_system_voice(names, "Auto", "en-US") == "Samantha"
    assert server._select_macos_system_voice(names, "Daniel", "de-DE") == "Anna"


@pytest.mark.parametrize(
    ("text", "configured", "expected"),
    [
        ("Ja, ich kann das für dich machen.", "auto", "de-DE"),
        ("Öffne bitte den Kalender.", "auto", "de-DE"),
        ("Gern.", "auto", "de-DE"),
        ("Bereit.", "auto", "de-DE"),
        ("Yes, I can do that for you.", "auto", "en-GB"),
        ("Ready.", "auto", "en-GB"),
        ("This is English.", "de-DE", "de-DE"),
        ("Das ist Deutsch.", "en-US", "en-US"),
    ],
)
def test_system_voice_detects_each_reply_language(text, configured, expected):
    assert server._infer_speech_language(text, configured) == expected


@pytest.mark.asyncio
async def test_voice_settings_persist_validated_speech_language(monkeypatch):
    saved = {}
    stopped = []

    async def stop_local_voice():
        stopped.append(True)

    monkeypatch.setattr(server, "_write_env_key", lambda key, value: saved.__setitem__(key, value))
    monkeypatch.setattr(server, "_reload_runtime_config", lambda: None)
    monkeypatch.setattr(server._local_voice_process, "stop", stop_local_voice)

    result = await server.api_save_voice_settings(server.VoiceSettingsUpdate(
        provider="system",
        system_voice="Auto",
        system_rate=170,
        speech_language="de-DE",
    ))

    assert result["success"] is True
    assert saved["JARVIS_SYSTEM_VOICE"] == "Auto"
    assert saved["JARVIS_SPEECH_LANGUAGE"] == "de-DE"
    assert stopped == [True]


@pytest.mark.asyncio
async def test_voice_settings_reject_unknown_speech_language(monkeypatch):
    writes = []
    monkeypatch.setattr(server, "_write_env_key", lambda *args: writes.append(args))

    result = await server.api_save_voice_settings(server.VoiceSettingsUpdate(
        speech_language="not-a-language",
    ))

    assert result.status_code == 400
    assert writes == []


@pytest.mark.asyncio
async def test_system_voice_rejects_header_only_audio(monkeypatch, tmp_path):
    output = tmp_path / "silent.wav"

    class FakeProcess:
        returncode = 0

        async def communicate(self):
            output.write_bytes(b"RIFF" + (b"\0" * 4092))
            return b"", b""

    async def fake_subprocess(*_args, **_kwargs):
        return FakeProcess()

    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_subprocess)

    assert await server._run_tts_command(["voice-test"], output) is None


def test_local_voice_timeout_is_bounded(monkeypatch):
    monkeypatch.setenv("JARVIS_TEST_TIMEOUT", "999999")
    assert server._voice_timeout("JARVIS_TEST_TIMEOUT", 300) == 900
    monkeypatch.setenv("JARVIS_TEST_TIMEOUT", "not-a-number")
    assert server._voice_timeout("JARVIS_TEST_TIMEOUT", 300) == 300


@pytest.mark.asyncio
async def test_tts_auto_falls_through_fish_system_and_local(monkeypatch, tmp_path):
    """The resident neural voice is the last resort, not the second choice.

    Automatic mode spends the cloud first, then the operating-system voice that
    costs no memory, and only reaches for the offline video voice when both are
    unavailable.
    """
    pack = _fake_voice_pack(tmp_path)
    calls = []

    async def local_voice(_text):
        calls.append("local")
        return b"FORM-local"

    async def failed_fish(_text):
        calls.append("fish")
        return None

    async def failed_system(_text):
        calls.append("system")
        return None

    monkeypatch.setattr(server, "LOCAL_VOICE_PACK_DIR", pack)
    monkeypatch.setattr(server, "TTS_PROVIDER", "auto")
    monkeypatch.setattr(server, "FISH_API_KEY", "configured")
    monkeypatch.setattr(server, "_synthesize_local_video_voice", local_voice)
    monkeypatch.setattr(server, "_synthesize_fish_speech", failed_fish)
    monkeypatch.setattr(server, "_synthesize_system_speech", failed_system)
    monkeypatch.setattr(server, "_session_tokens", {"tts_calls": 0})
    monkeypatch.setattr(server, "_append_usage_entry", lambda *_args: None)

    audio = await server.synthesize_speech("Status report.")

    assert audio == b"FORM-local"
    assert calls == ["fish", "system", "local"]
    assert server._last_tts_provider == "local"
