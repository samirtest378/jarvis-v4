from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

import actions
import server


@pytest.mark.parametrize(
    ("command", "url", "label"),
    [
        ("Open YouTube", "https://www.youtube.com/", "YouTube"),
        ("Open YouTube.", "https://www.youtube.com/", "YouTube"),
        ("Öffne Gmail", "https://mail.google.com/", "Gmail"),
        ("Starte Google Kalender", "https://calendar.google.com/", "Google Calendar"),
        ("Show Google Drive", "https://drive.google.com/", "Google Drive"),
        ("Open Chrome", "https://www.google.com/", "Chrome"),
        ("Öffne ChatGPT bitte.", "https://chatgpt.com/", "ChatGPT"),
        ("Ruf Fish Audio auf!", "https://fish.audio/", "Fish Audio"),
    ],
)
def test_fixed_web_shortcuts_do_not_need_an_llm(command, url, label):
    action = server.detect_action_fast(command)
    assert action == {"action": "open_url", "url": url, "label": label}


def test_calendar_question_is_not_mistaken_for_opening_google_calendar():
    assert server.detect_action_fast("What's on my calendar today?") == {"action": "check_calendar"}


@pytest.mark.parametrize(
    ("command", "url"),
    [
        ("Lies https://example.com/bericht", "https://example.com/bericht"),
        ("Read https://example.com/article", "https://example.com/article"),
        ("Fass diese Seite zusammen: https://example.com/news", "https://example.com/news"),
        ("Fasse diese Webseite zusammen: https://example.com/info", "https://example.com/info"),
    ],
)
def test_explicit_public_web_read_is_separate_from_opening_browser(command, url):
    assert server.detect_action_fast(command) == {"action": "read_web", "url": url}


def test_web_reader_never_invents_or_accepts_an_insecure_target():
    assert server.detect_action_fast("Lies diese Webseite") is None
    assert server.detect_action_fast("Lies http://localhost/private") is None
    assert server.extract_action("Ich lese das. [ACTION:READ_WEB] https://example.com/") == (
        "Ich lese das.",
        {"action": "read_web", "target": "https://example.com/"},
    )


def test_wake_context_recovers_shortened_offline_youtube_command():
    assert server.detect_action_fast("auf YouTube.", wake_triggered=True) == {
        "action": "open_url",
        "url": "https://www.youtube.com/",
        "label": "YouTube",
    }
    # The same ambiguous text typed into chat remains conversation, not an
    # automatic desktop action.
    assert server.detect_action_fast("auf YouTube.") is None


@pytest.mark.asyncio
async def test_wake_transcript_reaches_macos_chrome_launcher(monkeypatch):
    """Exercise the recovered wake transcript through the native action."""
    action = server.detect_action_fast("auf YouTube.", wake_triggered=True)
    assert action is not None
    monkeypatch.setattr(actions.sys, "platform", "darwin")
    captured = {}

    class CompletedProcess:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return CompletedProcess()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_browser(action["url"])

    assert result["success"] is True
    assert captured["executable"] == "osascript"
    script = captured["args"][1]
    assert 'tell application "Google Chrome"' in script
    assert 'open location "https://www.youtube.com/"' in script


@pytest.mark.parametrize(
    ("command", "action"),
    [
        ("Öffne Spotify", {"action": "open_app", "target": "spotify"}),
        ("Öffne Spotify.", {"action": "open_app", "target": "spotify"}),
        ("Open the Mail app", {"action": "open_app", "target": "mail"}),
        ("Starte Einstellungen", {"action": "open_app", "target": "einstellungen"}),
        ("Öffne das Terminal!", {"action": "open_app", "target": "terminal"}),
        ("Zeige Downloads", {"action": "open_folder", "target": "downloads"}),
        ("Zeige Downloads.", {"action": "open_folder", "target": "downloads"}),
        ("Open my Documents folder", {"action": "open_folder", "target": "documents"}),
    ],
)
def test_safe_native_shortcuts_do_not_need_an_llm(monkeypatch, tmp_path, command, action):
    monkeypatch.setattr(actions.Path, "home", classmethod(lambda cls: tmp_path))
    for folder in ("Downloads", "Documents"):
        (tmp_path / folder).mkdir(exist_ok=True)
    assert server.detect_action_fast(command) == action


def test_unknown_app_is_not_turned_into_a_system_command():
    assert server.detect_action_fast("Open definitely-not-a-real-app") is None
    assert server.detect_action_fast("Open driver settings") is None
    assert actions.resolve_application_name("definitely-not-a-real-app") is None


@pytest.mark.parametrize(
    ("command", "action"),
    [
        ("Was steht heute in meinem Kalender?", "check_calendar"),
        ("Habe ich heute Termine?", "check_calendar"),
        ("Was ist mein nächster Termin?", "check_calendar"),
        ("Prüfe meine E-Mails.", "check_mail"),
        ("Habe ich neue Mails?", "check_mail"),
        ("Was ist in meinem Posteingang?", "check_mail"),
        ("Schau auf meinen Bildschirm.", "describe_screen"),
        ("Welche Apps sind offen?", "describe_screen"),
        ("Meine Aufgaben bitte.", "check_tasks"),
        ("Wie ist der Stand?", "check_dispatch"),
        ("Wie viel kostet es?", "check_usage"),
        ("Öffne Claude.", "open_terminal"),
    ],
)
def test_common_german_spoken_commands_route_without_cloud_ai(command, action):
    result = server.detect_action_fast(command)
    assert result is not None
    assert result["action"] == action


@pytest.mark.parametrize(
    ("response", "clean", "action"),
    [
        (
            "Right away, sir. [ACTION:OPEN_APP] Spotify",
            "Right away, sir.",
            {"action": "open_app", "target": "Spotify"},
        ),
        (
            "Done, sir. [ACTION:OPEN_FOLDER] Downloads",
            "Done, sir.",
            {"action": "open_folder", "target": "Downloads"},
        ),
        (
            "Ich prüfe das. [ACTION:CHECK_CALENDAR]",
            "Ich prüfe das.",
            {"action": "check_calendar", "target": ""},
        ),
        (
            "Ich sehe nach. [ACTION:CHECK_MAIL]",
            "Ich sehe nach.",
            {"action": "check_mail", "target": ""},
        ),
    ],
)
def test_model_app_and_folder_actions_are_parsed(response, clean, action):
    assert server.extract_action(response) == (clean, action)


@pytest.mark.asyncio
async def test_windows_browser_uses_installed_chrome_without_shell(monkeypatch, tmp_path):
    chrome = tmp_path / "Google" / "Chrome" / "Application" / "chrome.exe"
    chrome.parent.mkdir(parents=True)
    chrome.write_bytes(b"")
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    captured = {}

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_browser("https://www.youtube.com/")

    assert result["success"] is True
    assert Path(captured["executable"]) == chrome
    assert captured["args"] == ("https://www.youtube.com/",)


@pytest.mark.asyncio
async def test_browser_rejects_non_url_input_before_launch(monkeypatch):
    monkeypatch.setattr(actions.sys, "platform", "win32")
    result = await actions.open_browser("javascript:alert(1)")
    assert result["success"] is False
    assert "safe" in result["confirmation"].lower()


@pytest.mark.asyncio
async def test_windows_safe_app_launch_uses_fixed_executable_without_shell(monkeypatch):
    monkeypatch.setattr(actions.sys, "platform", "win32")
    captured = {}

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_application("rechner")

    assert result["success"] is True
    assert captured["executable"] == "calc.exe"
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_windows_terminal_app_uses_known_launcher_without_shell(monkeypatch):
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions.shutil, "which", lambda name: "C:/Windows/wt.exe" if name == "wt.exe" else None)
    captured = {}

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_application("Terminal.")

    assert result["success"] is True
    assert captured["executable"] == "C:/Windows/wt.exe"
    assert captured["args"] == ()
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("spoken", "folder"),
    [("Mail", "outlook:inbox"), ("Kalender", "outlook:calendar")],
)
async def test_windows_mail_and_calendar_open_classic_outlook_directly(monkeypatch, tmp_path, spoken, folder):
    outlook = tmp_path / "Microsoft Office" / "root" / "Office16" / "OUTLOOK.EXE"
    outlook.parent.mkdir(parents=True)
    outlook.write_bytes(b"exe")
    captured = {}
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setenv("PROGRAMFILES", str(tmp_path))
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_application(spoken)

    assert result["success"] is True
    assert Path(captured["executable"]) == outlook
    assert captured["args"] == ("/select", folder)


@pytest.mark.asyncio
async def test_windows_opens_start_menu_shortcuts_and_files_without_cmd(monkeypatch, tmp_path):
    shortcut = tmp_path / "Programs" / "Blender.lnk"
    shortcut.parent.mkdir(parents=True)
    shortcut.write_bytes(b"shortcut")
    document = tmp_path / "Offer & Notes.txt"
    document.write_text("safe", encoding="utf-8")
    opened = []

    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions, "_application_search_roots", lambda: [shortcut.parent])
    monkeypatch.setattr(actions.os, "startfile", lambda target: opened.append(target), raising=False)

    app_result = await actions.open_application("Blender")
    file_result = await actions.open_path(str(document))

    assert app_result["success"] is True
    assert file_result["success"] is True
    assert opened == [str(shortcut), str(document)]


def test_windows_app_search_recurses_through_start_menu_groups(monkeypatch, tmp_path):
    start_menu = tmp_path / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    shortcut = start_menu / "Creative Tools" / "Blender 4.3.lnk"
    shortcut.parent.mkdir(parents=True)
    shortcut.write_bytes(b"shortcut")

    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(tmp_path))
    monkeypatch.delenv("PROGRAMDATA", raising=False)
    monkeypatch.delenv("PROGRAMFILES", raising=False)
    monkeypatch.delenv("PROGRAMFILES(X86)", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)

    assert actions.find_installed_application("Blender") == shortcut


def test_windows_known_folders_follow_redirected_user_shell_paths(monkeypatch, tmp_path):
    redirected = tmp_path / "OneDrive" / "Documents"
    redirected.mkdir(parents=True)

    class Key:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    fake_winreg = types.SimpleNamespace(
        HKEY_CURRENT_USER=object(),
        OpenKey=lambda *_args: Key(),
        QueryValueEx=lambda _key, name: (str(redirected), 1) if name == "Personal" else ("", 1),
    )
    monkeypatch.setitem(sys.modules, "winreg", fake_winreg)
    monkeypatch.setattr(actions.sys, "platform", "win32")

    assert actions.resolve_known_folder("Dokumente") == redirected


@pytest.mark.asyncio
async def test_windows_notes_and_music_have_native_safe_fallbacks(monkeypatch):
    monkeypatch.setattr(actions.sys, "platform", "win32")
    launched = []

    async def fake_exec(executable, *args, **_kwargs):
        launched.append((executable, args))
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)

    assert (await actions.open_application("Notizen"))["success"] is True
    assert (await actions.open_application("Musik"))["success"] is True
    assert launched == [
        ("notepad.exe", ()),
        ("explorer.exe", ("mswindowsmusic:",)),
    ]


@pytest.mark.asyncio
async def test_linux_opens_installed_system_settings_without_a_shell(monkeypatch):
    monkeypatch.setattr(actions.sys, "platform", "linux")
    monkeypatch.setattr(
        actions.shutil,
        "which",
        lambda name: "/usr/bin/gnome-control-center" if name == "gnome-control-center" else None,
    )
    captured = {}

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_application("Einstellungen")

    assert result["success"] is True
    assert captured["executable"] == "/usr/bin/gnome-control-center"
    assert captured["args"] == ()
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_linux_desktop_entry_uses_native_gio_launcher(monkeypatch, tmp_path):
    desktop_entry = tmp_path / "org.blender.Blender.desktop"
    desktop_entry.write_text("[Desktop Entry]\nName=Blender\n", encoding="utf-8")
    captured = {}
    monkeypatch.setattr(actions.sys, "platform", "linux")
    monkeypatch.setattr(actions, "find_installed_application", lambda name: desktop_entry)
    monkeypatch.setattr(actions.shutil, "which", lambda name: "/usr/bin/gio" if name == "gio" else None)

    class Completed:
        returncode = 0

        async def communicate(self):
            return b"", b""

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return Completed()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    result = await actions.open_application("Blender")

    assert result["success"] is True
    assert captured["executable"] == "/usr/bin/gio"
    assert captured["args"] == ("launch", str(desktop_entry))
    assert "shell" not in captured["kwargs"]


@pytest.mark.asyncio
async def test_standard_folder_launch_rejects_arbitrary_paths(monkeypatch, tmp_path):
    monkeypatch.setattr(actions.sys, "platform", "win32")
    monkeypatch.setattr(actions, "_windows_known_folder", lambda _relative: tmp_path / "Downloads")
    (tmp_path / "Downloads").mkdir()
    captured = {}

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return object()

    monkeypatch.setattr(actions.asyncio, "create_subprocess_exec", fake_exec)
    accepted = await actions.open_known_folder("Downloads")
    rejected = await actions.open_known_folder("../../Windows/System32")

    assert accepted["success"] is True
    assert captured["executable"] == "explorer.exe"
    assert captured["args"] == (str(tmp_path / "Downloads"),)
    assert rejected["success"] is False


@pytest.mark.parametrize(
    ("action", "user_request"),
    [
        ("browse", "Open YouTube"),
        ("screen", "What is on my screen?"),
        ("remember", "Merke dir, dass ich dunkle UIs mag"),
        ("add_task", "Erinnere mich morgen an den Anruf"),
        ("prompt_project", "Arbeite an meinem Nova-Projekt weiter"),
        ("build", "Erstelle eine App für meine Aufgaben"),
        ("open_app", "Öffne Spotify"),
        ("open_folder", "Zeige meinen Downloads Ordner"),
        ("check_calendar", "Was steht in meinem Kalender?"),
        ("check_mail", "Prüfe meine Emails"),
    ],
)
def test_model_actions_require_matching_user_intent(action, user_request):
    assert server.action_allowed_for_request(action, user_request) is True


@pytest.mark.parametrize("action", [
    "build", "browse", "research", "open_terminal", "prompt_project",
    "add_task", "add_note", "complete_task", "remember", "create_note", "read_note", "screen",
    "open_app", "open_folder", "check_calendar", "check_mail",
])
def test_ordinary_chat_never_authorizes_a_model_action(action):
    assert server.action_allowed_for_request(action, "Reply with exactly JARVIS_WEBSOCKET_OK") is False


def test_viewing_the_calendar_is_not_mistaken_for_opening_the_app():
    """"Zeig meinen Kalender" asks for appointments, not for Calendar.app.

    The generic open-prefix matching strips the verb and would resolve the
    remaining "kalender" as an application name.
    """
    for phrasing in (
        "Zeig meinen Kalender",
        "zeige meinen kalender",
        "zeig mir meine termine",
        "show my calendar",
        "was steht heute im kalender",
    ):
        assert server.detect_action_fast(phrasing) == {"action": "check_calendar"}, phrasing

    for phrasing in ("zeig meine mails", "show me my inbox", "zeige meinen posteingang"):
        assert server.detect_action_fast(phrasing) == {"action": "check_mail"}, phrasing


def test_opening_the_calendar_website_still_wins_over_the_viewing_shortcut():
    assert server.detect_action_fast("öffne google kalender") == {
        "action": "open_url",
        "url": "https://calendar.google.com/",
        "label": "Google Calendar",
    }


def test_plain_google_opens_the_search_page_without_a_model():
    assert server.detect_action_fast("öffne google") == {
        "action": "open_url",
        "url": "https://www.google.com/",
        "label": "Google",
    }


def test_questions_and_open_ended_requests_still_reach_the_model():
    for phrasing in (
        "was ist die hauptstadt von frankreich",
        "fasse mir den artikel zusammen",
        "zeige mir wie man eine api baut",
    ):
        assert server.detect_action_fast(phrasing) is None, phrasing
