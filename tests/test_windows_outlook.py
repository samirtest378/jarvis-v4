from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from datetime import datetime

import pytest

import calendar_access
import mail_access
import server
import windows_outlook


class _Process:
    def __init__(self, response: dict, captured: dict):
        self.returncode = 0
        self._response = response
        self._captured = captured

    async def communicate(self, payload: bytes):
        self._captured["stdin"] = payload
        return json.dumps(self._response).encode(), b""


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell parser is available on Windows CI")
def test_outlook_bridge_is_valid_powershell_on_windows():
    executable = shutil.which("powershell.exe") or shutil.which("pwsh.exe")
    assert executable
    parser = (
        "$tokens=$null; $errors=$null; "
        "[void][System.Management.Automation.Language.Parser]::ParseInput([Console]::In.ReadToEnd(),[ref]$tokens,[ref]$errors); "
        "if ($errors.Count) { $errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }; exit 1 }"
    )
    result = subprocess.run(
        [executable, "-NoProfile", "-NonInteractive", "-Command", parser],
        input=windows_outlook._POWERSHELL_BRIDGE,
        text=True,
        capture_output=True,
        timeout=15,
        check=False,
    )
    assert result.returncode == 0, result.stderr


@pytest.mark.asyncio
async def test_outlook_bridge_keeps_dictation_out_of_powershell_source(monkeypatch):
    captured = {}
    hostile = 'Hello"; Remove-Item -Recurse C:\\Users; #'
    monkeypatch.setattr(windows_outlook.sys, "platform", "win32")
    monkeypatch.setattr(windows_outlook.shutil, "which", lambda name: "powershell.exe" if name == "powershell.exe" else None)

    async def fake_exec(executable, *args, **kwargs):
        captured.update(executable=executable, args=args, kwargs=kwargs)
        return _Process({"available": True, "source": "outlook", "sent": True}, captured)

    monkeypatch.setattr(windows_outlook.asyncio, "create_subprocess_exec", fake_exec)
    result = await windows_outlook.run_outlook_action(
        "send",
        recipients=["anna@example.com"],
        subject="Status",
        body=hostile,
    )

    assert result["sent"] is True
    assert captured["executable"] == "powershell.exe"
    assert hostile not in " ".join(captured["args"])
    request = json.loads(captured["stdin"])
    assert request["body"] == hostile
    assert captured["kwargs"]["stdin"] is asyncio.subprocess.PIPE


def test_outlook_bridge_accepts_only_fixed_operations():
    with pytest.raises(ValueError, match="Unsupported Outlook action"):
        asyncio.run(windows_outlook.run_outlook_action("run-any-command"))


def test_outlook_events_use_the_shared_calendar_shape():
    payload = {
        "available": True,
        "events": [
            {"title": "Review", "start": "2026-08-01T09:30:00+02:00", "all_day": False, "calendar": "Work"},
            {"title": "Holiday", "start": "2026-08-01T00:00:00+02:00", "all_day": True, "calendar": "Home"},
        ],
    }

    events = windows_outlook.outlook_events(payload)

    assert events[0]["start"] == "9:30 AM"
    assert events[0]["start_dt"] == datetime(2026, 8, 1, 9, 30)
    assert events[1]["start"] == "ALL_DAY"


@pytest.mark.asyncio
async def test_windows_mail_reads_and_sends_through_outlook_without_confirmation(monkeypatch):
    calls = []
    monkeypatch.setattr(mail_access.sys, "platform", "win32")

    async def fake_outlook(action, **kwargs):
        calls.append((action, kwargs))
        if action == "unread":
            return {
                "available": True,
                "source": "outlook",
                "total": 1,
                "account": "Work",
                "messages": [{"sender": "Anna", "subject": "Review", "date": "", "read": False}],
            }
        if action == "send":
            return {"available": True, "source": "outlook", "sent": True}
        raise AssertionError(action)

    monkeypatch.setattr(mail_access, "run_outlook_action", fake_outlook)

    unread = await mail_access.get_unread_count()
    messages = await mail_access.get_unread_messages(5)
    sent = await mail_access.send_mail("anna@example.com", "Status", "Alles läuft.")

    assert unread == {"total": 1, "accounts": {"Work": 1}, "available": True, "source": "outlook"}
    assert messages[0]["subject"] == "Review"
    assert sent["success"] is True
    assert sent["via"] == "outlook"
    assert calls[-1] == (
        "send",
        {"recipients": ["anna@example.com"], "subject": "Status", "body": "Alles läuft.", "timeout": 45},
    )


@pytest.mark.asyncio
async def test_windows_calendar_refresh_uses_outlook(monkeypatch):
    monkeypatch.setattr(calendar_access.sys, "platform", "win32")
    monkeypatch.setattr(calendar_access, "_event_cache", [])
    monkeypatch.setattr(calendar_access, "_cache_time", 0.0)
    monkeypatch.setattr(calendar_access, "_native_available", False)
    monkeypatch.setattr(calendar_access, "_native_error", "")

    async def fake_outlook(action, **kwargs):
        assert action == "calendar"
        assert kwargs == {"limit": 100}
        return {
            "available": True,
            "source": "outlook",
            "events": [{
                "title": "Planning",
                "start": "2026-08-01T11:00:00+02:00",
                "end": "2026-08-01T12:00:00+02:00",
                "all_day": False,
                "calendar": "Outlook",
            }],
        }

    monkeypatch.setattr(calendar_access, "run_outlook_action", fake_outlook)
    await calendar_access.refresh_cache()

    assert calendar_access.native_calendar_status()["available"] is True
    assert (await calendar_access.get_todays_events())[0]["title"] == "Planning"


@pytest.mark.asyncio
async def test_server_uses_native_outlook_on_windows_when_google_is_not_connected(monkeypatch):
    class NotConnected:
        configured = False

    async def refresh():
        return None

    async def events():
        return [{"title": "Planning", "start": "11:00 AM", "all_day": False, "calendar": "Outlook"}]

    async def unread_count():
        return {"total": 1, "accounts": {"Outlook": 1}, "available": True}

    async def unread_messages(count=5):
        return [{"sender": "Anna", "subject": "Review", "read": False, "date": ""}]

    monkeypatch.setattr(server.sys, "platform", "win32")
    monkeypatch.setattr(server, "google_account_client", NotConnected())
    monkeypatch.setattr(server, "refresh_calendar_cache", refresh)
    monkeypatch.setattr(server, "native_calendar_status", lambda: {"available": True})
    monkeypatch.setattr(server, "get_todays_events", events)
    monkeypatch.setattr(server, "get_unread_count", unread_count)
    monkeypatch.setattr(server, "get_unread_messages", unread_messages)

    assert "Planning" in await server._do_calendar_lookup()
    mail = await server._do_mail_lookup()
    assert "Anna regarding Review" in mail
    assert "Sie haben einen Termin" in await server._do_calendar_lookup("de")
    assert "ungelesene Nachricht" in await server._do_mail_lookup("de")
