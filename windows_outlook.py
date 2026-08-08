"""Safe Windows bridge for classic Outlook mail and calendar.

The PowerShell program is fixed source code. User-controlled recipients,
subjects, bodies and search terms travel only as JSON on standard input, so
dictation can never become part of a command line or script.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import sys
from pathlib import Path
from typing import Any


log = logging.getLogger("jarvis.windows-outlook")

_POWERSHELL_BRIDGE = r'''
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$WarningPreference = "SilentlyContinue"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

function Emit-Json($value) {
    [Console]::Out.WriteLine(($value | ConvertTo-Json -Compress -Depth 7))
}

function Clean-Text($value, [int]$limit) {
    $text = [string]$value
    $text = $text -replace '[\r\n\t]+', ' '
    $text = $text.Trim()
    if ($text.Length -gt $limit) { return $text.Substring(0, $limit) }
    return $text
}

function Message-Record($message, [bool]$includeBody) {
    $preview = ""
    if ($includeBody) {
        try { $preview = Clean-Text $message.Body 3000 } catch { $preview = "" }
    } else {
        try { $preview = Clean-Text $message.Body 150 } catch { $preview = "" }
    }
    $sender = ""
    try { $sender = Clean-Text $message.SenderName 200 } catch { $sender = "" }
    if (-not $sender) {
        try { $sender = Clean-Text $message.SenderEmailAddress 200 } catch { $sender = "" }
    }
    $received = ""
    try { $received = ([datetime]$message.ReceivedTime).ToString("o") } catch { $received = "" }
    return [PSCustomObject]@{
        sender = $sender
        subject = Clean-Text $message.Subject 300
        date = $received
        read = -not [bool]$message.UnRead
        preview = $preview
        content = $(if ($includeBody) { $preview } else { "" })
    }
}

try {
    $requestText = [Console]::In.ReadToEnd()
    if (-not $requestText -or $requestText.Length -gt 131072) { throw "Invalid request" }
    $request = $requestText | ConvertFrom-Json
    $outlook = New-Object -ComObject Outlook.Application
    $namespace = $outlook.GetNamespace("MAPI")
    $action = [string]$request.action

    if ($action -eq "calendar") {
        $folder = $namespace.GetDefaultFolder(9)
        $items = $folder.Items
        $items.Sort("[Start]")
        $items.IncludeRecurrences = $true
        $start = (Get-Date).Date
        $end = $start.AddDays(1)
        $filter = "[Start] >= '" + $start.ToString("g") + "' AND [Start] < '" + $end.ToString("g") + "'"
        $today = $items.Restrict($filter)
        $events = @()
        $limit = [Math]::Min([Math]::Max([int]$request.limit, 1), 100)
        for ($index = 1; $index -le [Math]::Min($today.Count, $limit); $index++) {
            $item = $today.Item($index)
            $events += [PSCustomObject]@{
                title = Clean-Text $item.Subject 300
                start = ([datetime]$item.Start).ToString("o")
                end = ([datetime]$item.End).ToString("o")
                all_day = [bool]$item.AllDayEvent
                calendar = Clean-Text $folder.Name 120
            }
        }
        Emit-Json ([PSCustomObject]@{available=$true; source="outlook"; events=@($events)})
        exit 0
    }

    if ($action -eq "send") {
        $message = $outlook.CreateItem(0)
        $message.To = (@($request.recipients) -join ";")
        $message.Subject = [string]$request.subject
        $message.Body = [string]$request.body
        $message.Send()
        Emit-Json ([PSCustomObject]@{available=$true; source="outlook"; sent=$true})
        exit 0
    }

    $inbox = $namespace.GetDefaultFolder(6)
    $items = $inbox.Items
    $items.Sort("[ReceivedTime]", $true)
    $limit = [Math]::Min([Math]::Max([int]$request.limit, 1), 50)

    if ($action -eq "unread") {
        $items = $items.Restrict("[Unread] = true")
    }

    if ($action -eq "search" -or $action -eq "read") {
        $query = Clean-Text $request.query 200
        $matches = @()
        $scanLimit = [Math]::Min($items.Count, 500)
        for ($index = 1; $index -le $scanLimit; $index++) {
            $item = $items.Item($index)
            $subject = [string]$item.Subject
            $sender = [string]$item.SenderName
            if ($subject.IndexOf($query, [System.StringComparison]::OrdinalIgnoreCase) -ge 0 -or
                $sender.IndexOf($query, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) {
                $matches += (Message-Record $item ($action -eq "read"))
                if ($action -eq "read" -or $matches.Count -ge $limit) { break }
            }
        }
        Emit-Json ([PSCustomObject]@{
            available=$true
            source="outlook"
            message=$(if ($action -eq "read" -and $matches.Count) { $matches[0] } else { $null })
            messages=$(if ($action -eq "search") { @($matches) } else { @() })
        })
        exit 0
    }

    $messages = @()
    for ($index = 1; $index -le [Math]::Min($items.Count, $limit); $index++) {
        $messages += (Message-Record ($items.Item($index)) $false)
    }
    Emit-Json ([PSCustomObject]@{
        available=$true
        source="outlook"
        total=$(if ($action -eq "unread") { [int]$items.Count } else { [int]$inbox.UnReadItemCount })
        account=Clean-Text ([string]$namespace.CurrentUser.Name) 120
        messages=@($messages)
    })
} catch {
    Emit-Json ([PSCustomObject]@{
        available=$false
        source="outlook"
        error="Classic Outlook is not installed, configured, or available to JARVIS."
    })
}
'''


def _powershell_executable() -> str | None:
    if sys.platform != "win32":
        return None
    return shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")


def classic_outlook_installed() -> bool:
    """Detect classic Outlook without launching it or prompting for access."""
    if sys.platform != "win32":
        return False
    if shutil.which("OUTLOOK.EXE") or shutil.which("outlook.exe"):
        return True
    roots = [
        os.getenv("PROGRAMFILES", ""),
        os.getenv("PROGRAMFILES(X86)", ""),
    ]
    relatives = (
        ("Microsoft Office", "root", "Office16", "OUTLOOK.EXE"),
        ("Microsoft Office", "Office16", "OUTLOOK.EXE"),
    )
    if any(Path(root, *relative).is_file() for root in roots if root for relative in relatives):
        return True
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Outlook.Application\CLSID"):
            return True
    except (ImportError, OSError):
        return False


async def run_outlook_action(
    action: str,
    *,
    limit: int = 10,
    query: str = "",
    recipients: list[str] | None = None,
    subject: str = "",
    body: str = "",
    timeout: float = 30.0,
) -> dict[str, Any]:
    """Run one allow-listed Outlook operation and return validated JSON."""
    if action not in {"calendar", "unread", "recent", "search", "read", "send"}:
        raise ValueError("Unsupported Outlook action")
    executable = _powershell_executable()
    if not executable:
        return {"available": False, "source": "outlook", "error": "PowerShell is unavailable."}
    request = {
        "action": action,
        "limit": max(1, min(int(limit), 100)),
        "query": str(query)[:200],
        "recipients": list(recipients or [])[:20],
        "subject": str(subject)[:200],
        "body": str(body)[:20_000],
    }
    encoded = json.dumps(request, ensure_ascii=False).encode("utf-8")
    process = await asyncio.create_subprocess_exec(
        executable,
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        _POWERSHELL_BRIDGE,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(encoded), timeout=timeout)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()
        return {"available": False, "source": "outlook", "error": "Outlook took too long to respond."}
    if process.returncode != 0 or not stdout or len(stdout) > 2 * 1024 * 1024:
        detail = stderr.decode("utf-8", errors="replace").strip()[:160]
        log.warning("Outlook bridge failed: %s", detail or process.returncode)
        return {"available": False, "source": "outlook", "error": "Outlook could not complete the request."}
    try:
        result = json.loads(stdout.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"available": False, "source": "outlook", "error": "Outlook returned an invalid response."}
    if not isinstance(result, dict) or result.get("source") != "outlook":
        return {"available": False, "source": "outlook", "error": "Outlook returned an invalid response."}
    return result


def outlook_events(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize bridge calendar records into JARVIS's shared event shape."""
    if not payload.get("available") or not isinstance(payload.get("events"), list):
        return []
    events: list[dict[str, Any]] = []
    for item in payload["events"][:100]:
        if not isinstance(item, dict):
            continue
        try:
            from datetime import datetime
            start = datetime.fromisoformat(str(item.get("start", ""))).replace(tzinfo=None)
        except ValueError:
            continue
        all_day = bool(item.get("all_day"))
        events.append({
            "calendar": str(item.get("calendar") or "Outlook")[:120],
            "title": str(item.get("title") or "Untitled event")[:300],
            "start": "ALL_DAY" if all_day else start.strftime("%I:%M %p").lstrip("0"),
            "start_dt": start,
            "all_day": all_day,
        })
    return events


def outlook_messages(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not payload.get("available") or not isinstance(payload.get("messages"), list):
        return []
    return [item for item in payload["messages"][:50] if isinstance(item, dict)]
