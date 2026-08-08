"""
JARVIS Screen Awareness — see what's on the user's screen.

Two capabilities:
1. Window/app list via AppleScript (fast, text-based)
2. Screenshot via screencapture → Claude vision API (sees everything)
"""

import asyncio
import base64
import json
import logging
import shutil
import sys
import tempfile
from pathlib import Path

from config import LLM_MODEL

log = logging.getLogger("jarvis.screen")


async def get_active_windows() -> list[dict]:
    """Get list of visible windows with app name, window title, and position.

    Uses AppleScript + System Events to enumerate windows.
    Returns list of {"app": str, "title": str, "frontmost": bool}.
    """
    if sys.platform == "win32":
        powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")
        if not powershell:
            return []
        script = (
            "$OutputEncoding=[Console]::OutputEncoding=[Text.Encoding]::UTF8; "
            "Add-Type -TypeDefinition 'using System; using System.Runtime.InteropServices; "
            "public static class JarvisWindow { "
            "[DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow(); "
            "[DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint processId); }'; "
            "$foregroundPid=[uint32]0; $handle=[JarvisWindow]::GetForegroundWindow(); "
            "[void][JarvisWindow]::GetWindowThreadProcessId($handle,[ref]$foregroundPid); "
            "$items=Get-Process | Where-Object {$_.MainWindowTitle} | ForEach-Object {"
            "[PSCustomObject]@{app=$_.ProcessName;title=$_.MainWindowTitle;frontmost=($_.Id -eq $foregroundPid)}}; "
            "$items | ConvertTo-Json -Compress"
        )
        try:
            proc = await asyncio.create_subprocess_exec(
                powershell, "-NoProfile", "-NonInteractive", "-Command", script,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=8)
            if proc.returncode != 0 or not stdout.strip():
                return []
            payload = json.loads(stdout.decode("utf-8-sig"))
            values = payload if isinstance(payload, list) else [payload]
            return [
                {
                    "app": str(item.get("app", "")).strip(),
                    "title": str(item.get("title", "")).strip(),
                    "frontmost": bool(item.get("frontmost", False)),
                }
                for item in values
                if isinstance(item, dict) and str(item.get("title", "")).strip()
            ]
        except (asyncio.TimeoutError, OSError, ValueError) as exc:
            log.warning("Windows window listing failed: %s", type(exc).__name__)
            return []

    if sys.platform != "darwin":
        wmctrl = shutil.which("wmctrl")
        if not wmctrl:
            return []
        try:
            proc = await asyncio.create_subprocess_exec(
                wmctrl, "-l", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
            windows = []
            for line in stdout.decode(errors="replace").splitlines():
                parts = line.split(None, 3)
                if len(parts) == 4 and parts[3].strip():
                    windows.append({"app": "Window", "title": parts[3].strip(), "frontmost": False})
            return windows
        except (asyncio.TimeoutError, OSError):
            return []

    # Use a simpler approach that's more permission-friendly
    script = """
set windowList to ""
tell application "System Events"
    set frontApp to name of first application process whose frontmost is true
    set visibleApps to every application process whose visible is true
    repeat with proc in visibleApps
        set appName to name of proc
        try
            set winCount to count of windows of proc
            if winCount > 0 then
                repeat with w in (windows of proc)
                    try
                        set winTitle to name of w
                        if winTitle is not "" and winTitle is not missing value then
                            set windowList to windowList & appName & "|||" & winTitle & "|||" & (appName = frontApp) & linefeed
                        end if
                    end try
                end repeat
            end if
        end try
    end repeat
end tell
return windowList
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=5)

        if proc.returncode != 0:
            log.warning(f"get_active_windows failed: {stderr.decode()[:200]}")
            return []

        windows = []
        for line in stdout.decode().strip().split("\n"):
            parts = line.strip().split("|||")
            if len(parts) >= 3:
                windows.append({
                    "app": parts[0].strip(),
                    "title": parts[1].strip(),
                    "frontmost": parts[2].strip().lower() == "true",
                })
        return windows

    except asyncio.TimeoutError:
        log.warning("get_active_windows timed out")
        return []
    except Exception as e:
        log.warning(f"get_active_windows error: {e}")
        return []


async def get_running_apps() -> list[str]:
    """Get list of running application names (visible only)."""
    if sys.platform != "darwin":
        windows = await get_active_windows()
        return list(dict.fromkeys(window["app"] for window in windows if window.get("app")))
    script = """
tell application "System Events"
    set appNames to name of every application process whose visible is true
    set output to ""
    repeat with a in appNames
        set output to output & a & linefeed
    end repeat
    return output
end tell
"""
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        if proc.returncode == 0:
            return [a.strip() for a in stdout.decode().strip().split("\n") if a.strip()]
        return []
    except Exception as e:
        log.warning(f"get_running_apps error: {e}")
        return []


async def take_screenshot(display_only: bool = True) -> str | None:
    """Take a screenshot and return base64-encoded PNG.

    Args:
        display_only: If True, capture main display only. If False, all displays.

    Returns:
        Base64-encoded PNG string, or None on failure.
    """
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        tmp_path = f.name

    try:
        if sys.platform == "win32":
            powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")
            if not powershell:
                return None
            bounds = "[Windows.Forms.Screen]::PrimaryScreen.Bounds" if display_only else "[Windows.Forms.SystemInformation]::VirtualScreen"
            script = (
                "Add-Type -AssemblyName System.Windows.Forms; Add-Type -AssemblyName System.Drawing; "
                f"$b={bounds}; "
                "$bmp=New-Object Drawing.Bitmap $b.Width,$b.Height; "
                "$g=[Drawing.Graphics]::FromImage($bmp); "
                "$g.CopyFromScreen($b.Location,[Drawing.Point]::Empty,$b.Size); "
                "$bmp.Save($args[0],[Drawing.Imaging.ImageFormat]::Png); $g.Dispose(); $bmp.Dispose()"
            )
            cmd = [powershell, "-NoProfile", "-NonInteractive", "-Command", script, tmp_path]
        elif sys.platform == "darwin":
            cmd = ["screencapture", "-x"]  # -x = no sound
            if display_only:
                cmd.append("-m")  # main display only
            cmd.append(tmp_path)
        else:
            gnome = shutil.which("gnome-screenshot")
            spectacle = shutil.which("spectacle")
            scrot = shutil.which("scrot")
            if gnome:
                cmd = [gnome, "-f", tmp_path]
            elif spectacle:
                cmd = [spectacle, "-b", "-n", "-o", tmp_path]
            elif scrot:
                cmd = [scrot, tmp_path]
            else:
                return None

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)

        if proc.returncode != 0 or not Path(tmp_path).exists():
            log.warning("Screenshot capture failed")
            return None

        data = Path(tmp_path).read_bytes()
        log.info(f"Screenshot captured: {len(data)} bytes")
        return base64.b64encode(data).decode()

    except asyncio.TimeoutError:
        log.warning("Screenshot timed out")
        return None
    except Exception as e:
        log.warning(f"Screenshot error: {e}")
        return None
    finally:
        try:
            Path(tmp_path).unlink(missing_ok=True)
        except Exception:
            pass


async def describe_screen(anthropic_client, language: str = "en") -> str:
    """Describe what's on the user's screen.

    Tries screenshot + vision first. Falls back to window list + LLM summary.
    """
    german = language == "de"
    # Try screenshot + vision
    screenshot_b64 = await take_screenshot()
    if screenshot_b64 and anthropic_client:
        try:
            response = await anthropic_client.messages.create(
                model=LLM_MODEL,
                max_tokens=300,
                system=(
                    "You are JARVIS analyzing a screenshot of the user's desktop. "
                    "Describe what you see concisely: which apps are open, what the user "
                    "appears to be working on, any notable content visible. "
                    "Be specific about app names, file names, URLs, code, or documents visible. "
                    f"2-4 sentences max. No markdown. Reply only in {'German' if german else 'English'}."
                ),
                messages=[{
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": "image/png",
                                "data": screenshot_b64,
                            },
                        },
                        {
                            "type": "text",
                            "text": "Was ist gerade auf meinem Bildschirm?" if german else "What's on my screen right now?",
                        },
                    ],
                }],
            )
            return response.content[0].text
        except Exception as e:
            log.warning(f"Vision call failed, falling back to window list: {e}")

    # Fallback: get window list and have LLM summarize
    windows = await get_active_windows()
    apps = await get_running_apps()

    if not windows and not apps:
        return (
            "Ich konnte Ihren Bildschirm nicht sehen. Möglicherweise fehlt die Bildschirmaufnahme-Berechtigung."
            if german else "I wasn't able to see your screen, sir. Screen recording permission may be needed."
        )

    # Build a text description for LLM to summarize
    context_parts = []
    if windows:
        for w in windows:
            marker = " (ACTIVE)" if w["frontmost"] else ""
            context_parts.append(f"{w['app']}: {w['title']}{marker}")

    if apps:
        window_apps = set(w["app"] for w in windows) if windows else set()
        bg_apps = [a for a in apps if a not in window_apps]
        if bg_apps:
            context_parts.append(f"Background apps: {', '.join(bg_apps)}")

    if anthropic_client and context_parts:
        try:
            response = await anthropic_client.messages.create(
                model=LLM_MODEL,
                max_tokens=100,
                system=(
                    "You are JARVIS. Given the user's open windows and apps, summarize "
                    "what they appear to be working on in 1-2 sentences. Natural voice, no markdown. "
                    f"Reply only in {'German' if german else 'English'}."
                ),
                messages=[{"role": "user", "content": "Open windows:\n" + "\n".join(context_parts)}],
            )
            return response.content[0].text
        except Exception:
            pass

    # Raw fallback
    if windows:
        active = next((w for w in windows if w["frontmost"]), None)
        result = (
            f"Sie haben {len(windows)} Fenster in {len(set(w['app'] for w in windows))} Apps geöffnet."
            if german else f"You have {len(windows)} windows open across {len(set(w['app'] for w in windows))} apps."
        )
        if active:
            result += (
                f" Im Vordergrund ist {active['app']}: {active['title']}."
                if german else f" Currently focused on {active['app']}: {active['title']}."
            )
        return result

    return (
        f"Laufende Apps: {', '.join(apps)}. Ich konnte die Fenstertitel nicht lesen."
        if german else f"Running apps: {', '.join(apps)}. Couldn't read window titles, sir."
    )


def format_windows_for_context(windows: list[dict]) -> str:
    """Format window list as context string for the LLM."""
    if not windows:
        return ""
    lines = ["Currently open on your desktop:"]
    for w in windows:
        marker = " (active)" if w["frontmost"] else ""
        lines.append(f"  - {w['app']}: {w['title']}{marker}")
    return "\n".join(lines)
