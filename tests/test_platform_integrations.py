from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

import actions
import screen
import server


class _CompletedProcess:
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr


class _InputProcess(_CompletedProcess):
    def __init__(self, stdout: bytes = b"", stderr: bytes = b"", returncode: int = 0):
        super().__init__(stdout, stderr, returncode)
        self.input = None

    async def communicate(self, input=None):
        self.input = input
        return self._stdout, self._stderr


@pytest.mark.asyncio
async def test_windows_project_terminal_starts_in_exact_directory(monkeypatch, tmp_path: Path):
    project = tmp_path / "Project With Spaces"
    project.mkdir()
    captured = {}
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions.shutil, "which", lambda name: "C:/Windows/wt.exe" if name == "wt.exe" else None)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return _CompletedProcess()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_claude_in_project(str(project), "Build the requested desktop app")

    assert result["success"] is True
    assert captured["executable"] == "C:/Windows/wt.exe"
    assert captured["args"][:2] == ("-d", str(project))
    assert captured["args"][-1] == "claude"
    assert "Build the requested desktop app" in (project / "CLAUDE.md").read_text(encoding="utf-8")


@pytest.mark.asyncio
async def test_existing_project_work_mode_keeps_its_claude_instructions(monkeypatch, tmp_path: Path):
    project = tmp_path / "Existing Project"
    project.mkdir()
    instructions = project / "CLAUDE.md"
    instructions.write_text("# Keep me\n", encoding="utf-8")
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions.shutil, "which", lambda name: "C:/Windows/wt.exe" if name == "wt.exe" else None)

    async def fake_exec(*args, **kwargs):
        return _CompletedProcess()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_claude_in_project(
        str(project),
        "Wait for the user",
        prepare_task=False,
    )

    assert result["success"] is True
    assert instructions.read_text(encoding="utf-8") == "# Keep me\n"


@pytest.mark.asyncio
async def test_windows_store_app_lookup_keeps_spoken_text_out_of_powershell(monkeypatch):
    query = 'Outlook"; Remove-Item C:\\\\Users\\\\Public; #'
    payload = json.dumps({
        "name": "Outlook (new)",
        "app_id": "Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookforWindows",
    }).encode()
    captured = {}
    process = _InputProcess(payload)
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions.shutil, "which", lambda name: "powershell.exe" if name == "powershell.exe" else None)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return process

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    match = await actions._find_windows_start_app(query)

    assert match == (
        "Outlook (new)",
        "Microsoft.OutlookForWindows_8wekyb3d8bbwe!Microsoft.OutlookforWindows",
    )
    assert query not in captured["args"][3]
    assert json.loads(process.input)["query"] == query
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_windows_store_app_launch_uses_os_app_id_without_shell(monkeypatch):
    captured = {}
    monkeypatch.setattr(actions.sys, "platform", "win32")

    async def fake_find(query):
        return "Outlook (new)", "Microsoft.Outlook_123!App"

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return _CompletedProcess()

    monkeypatch.setattr(actions, "_find_windows_start_app", fake_find)
    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions._open_windows_start_app("Outlook")

    assert result["success"] is True
    assert captured["executable"] == "explorer.exe"
    assert captured["args"] == ("shell:AppsFolder\\Microsoft.Outlook_123!App",)
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_windows_system_voice_prefers_matching_male_language_without_script_text(monkeypatch):
    captured = {}
    speech = 'Hallo "; Remove-Item C:\\\\Users\\\\Public; #'
    monkeypatch.setattr(server, "SPEECH_LANGUAGE", "auto")
    monkeypatch.setattr(server, "SYSTEM_TTS_VOICE", "Microsoft George - English (United Kingdom)")
    monkeypatch.setattr(server, "_system_tts_engine", lambda language=None: ("windows-sapi", "Windows default"))
    monkeypatch.setattr(server.shutil, "which", lambda name: "powershell.exe" if name == "powershell" else None)

    async def fake_run(command, output_path):
        captured.update(command=command, input_text=Path(command[-4]).read_text(encoding="utf-8"))
        return b"RIFFtest"

    monkeypatch.setattr(server, "_run_tts_command", fake_run)
    audio = await server._synthesize_system_speech(speech)

    assert audio == b"RIFFtest"
    script = captured["command"][4]
    assert "Gender -eq 'Male'" in script
    assert "TwoLetterISOLanguageName" in script
    assert speech not in script
    assert captured["input_text"] == speech


@pytest.mark.asyncio
async def test_windows_window_listing_uses_fixed_powershell_and_parses_json(monkeypatch):
    payload = json.dumps([
        {"app": "chrome", "title": "Gmail", "frontmost": True},
        {"app": "Code", "title": "JARVIS v4", "frontmost": False},
    ]).encode()
    captured = {}
    monkeypatch.setattr(screen.sys, "platform", "win32")
    monkeypatch.setattr(screen.shutil, "which", lambda name: "powershell.exe" if name == "powershell.exe" else None)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return _CompletedProcess(payload)

    monkeypatch.setattr(screen.asyncio, "create_subprocess_exec", fake_exec)
    windows = await screen.get_active_windows()

    assert [window["title"] for window in windows] == ["Gmail", "JARVIS v4"]
    assert windows[0]["frontmost"] is True
    assert captured["executable"] == "powershell.exe"
    assert captured["args"][:3] == ("-NoProfile", "-NonInteractive", "-Command")
    assert captured["kwargs"]["stdout"] is screen.asyncio.subprocess.PIPE


@pytest.mark.asyncio
async def test_windows_screenshot_is_local_png_and_uses_no_shell(monkeypatch):
    captured = {}
    monkeypatch.setattr(screen.sys, "platform", "win32")
    monkeypatch.setattr(screen.shutil, "which", lambda name: "powershell.exe" if name == "powershell.exe" else None)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        Path(args[-1]).write_bytes(b"\x89PNG\r\n\x1a\nlocal-test")
        return _CompletedProcess()

    monkeypatch.setattr(screen.asyncio, "create_subprocess_exec", fake_exec)
    encoded = await screen.take_screenshot()

    assert encoded is not None
    assert base64.b64decode(encoded).startswith(b"\x89PNG")
    assert captured["executable"] == "powershell.exe"
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_windows_all_display_screenshot_uses_virtual_desktop(monkeypatch):
    captured = {}
    monkeypatch.setattr(screen.sys, "platform", "win32")
    monkeypatch.setattr(screen.shutil, "which", lambda name: "powershell.exe" if name == "powershell.exe" else None)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        Path(args[-1]).write_bytes(b"\x89PNG\r\n\x1a\nall-displays")
        return _CompletedProcess()

    monkeypatch.setattr(screen.asyncio, "create_subprocess_exec", fake_exec)
    encoded = await screen.take_screenshot(display_only=False)

    assert encoded is not None
    assert "SystemInformation]::VirtualScreen" in captured["args"][3]


@pytest.mark.asyncio
async def test_non_macos_private_integrations_never_report_empty_data(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "google_account_client", type("NotConnected", (), {"configured": False})())

    async def refresh():
        return None

    async def unavailable_mail():
        return {"total": 0, "accounts": {}, "available": False, "source": "outlook"}

    monkeypatch.setattr(server, "refresh_calendar_cache", refresh)
    monkeypatch.setattr(server, "native_calendar_status", lambda: {"available": False})
    monkeypatch.setattr(server, "get_unread_count", unavailable_mail)
    calendar_message = await server._do_calendar_lookup()
    mail_message = await server._do_mail_lookup()

    assert "classic Outlook Calendar" in calendar_message
    assert "connect Google" in calendar_message
    assert "classic Outlook Mail" in mail_message
    assert "connect Google" in mail_message


@pytest.mark.asyncio
async def test_screen_lookup_answers_in_the_turn_language(monkeypatch):
    monkeypatch.setattr(server, "anthropic_client", None)

    async def windows():
        return [{"app": "Code", "title": "JARVIS v4", "frontmost": True}]

    monkeypatch.setattr(server, "get_active_windows", windows)

    assert "Im Vordergrund ist Code" in await server._do_screen_lookup("de")
    assert "Currently focused on Code" in await server._do_screen_lookup("en")


@pytest.mark.asyncio
async def test_windows_recent_project_opens_in_file_explorer_without_shell(monkeypatch, tmp_path: Path):
    project = tmp_path / "Project With & Characters"
    project.mkdir()
    captured = {}
    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "recently_built", [{"name": "Safe Project", "path": str(project), "time": 1.0}])

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return _CompletedProcess()

    monkeypatch.setattr(server.asyncio, "create_subprocess_exec", fake_exec)
    message = await server.handle_show_recent()

    assert captured["executable"] == "explorer.exe"
    assert captured["args"] == (str(project),)
    assert "shell" not in captured["kwargs"]
    assert "File Explorer" in message


def test_background_window_title_context_requires_explicit_desktop_opt_in(monkeypatch):
    monkeypatch.setattr(server.sys, "platform", "darwin")
    monkeypatch.delenv("JARVIS_BACKGROUND_SCREEN_CONTEXT", raising=False)
    assert server._background_screen_context_enabled() is False

    monkeypatch.setenv("JARVIS_BACKGROUND_SCREEN_CONTEXT", "1")
    assert server._background_screen_context_enabled() is True

    monkeypatch.setattr(server.sys, "platform", "win32")
    assert server._background_screen_context_enabled() is True

    monkeypatch.setattr(server.sys, "platform", "linux")
    assert server._background_screen_context_enabled() is True
