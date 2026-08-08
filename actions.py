"""
JARVIS Action Executor — AppleScript-based system actions.

Execute actions IMMEDIATELY, before generating any LLM response.
Each function returns {"success": bool, "confirmation": str}.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

log = logging.getLogger("jarvis.actions")

DESKTOP_PATH = Path.home() / "Desktop"


# The catalogue below is a set of fast, well-labelled aliases, not a limit:
# `resolve_application_name()` falls back to whatever is actually installed, so
# any application on the machine can be opened by name. Spoken text still never
# reaches a shell — every launch goes through an argument list, and the target
# has to exist on disk before it is used.
_APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "safari": "safari",
    "firefox": "firefox",
    "edge": "edge",
    "microsoft edge": "edge",
    "mail": "mail",
    "apple mail": "mail",
    "outlook": "outlook",
    "calendar": "calendar",
    "kalender": "calendar",
    "notes": "notes",
    "notizen": "notes",
    "spotify": "spotify",
    "music": "music",
    "musik": "music",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "vscode": "vscode",
    "finder": "files",
    "file explorer": "files",
    "explorer": "files",
    "datei explorer": "files",
    "dateiexplorer": "files",
    "files": "files",
    "dateien": "files",
    "settings": "settings",
    "system settings": "settings",
    "einstellungen": "settings",
    "systemeinstellungen": "settings",
    "calculator": "calculator",
    "rechner": "calculator",
    "notepad": "notepad",
    "editor": "notepad",
    "terminal": "terminal",
    "konsole": "terminal",
    "command prompt": "terminal",
    "eingabeaufforderung": "terminal",
    "powershell": "terminal",
    "task manager": "task_manager",
    "taskmanager": "task_manager",
    "activity monitor": "task_manager",
    "aktivitätsanzeige": "task_manager",
    "system monitor": "task_manager",
}

_APP_LABELS = {
    "chrome": "Chrome",
    "safari": "Safari",
    "firefox": "Firefox",
    "edge": "Microsoft Edge",
    "mail": "Mail",
    "outlook": "Outlook",
    "calendar": "Calendar",
    "notes": "Notes",
    "spotify": "Spotify",
    "music": "Music",
    "vscode": "Visual Studio Code",
    "files": "Finder" if sys.platform == "darwin" else "File Explorer" if sys.platform == "win32" else "Files",
    "settings": "System Settings" if sys.platform == "darwin" else "Settings",
    "calculator": "Calculator",
    "notepad": "Notepad",
    "terminal": "Terminal",
    "task_manager": "Activity Monitor" if sys.platform == "darwin" else "Task Manager" if sys.platform == "win32" else "System Monitor",
}

# Same idea for folders: these are shortcuts with nice names, while
# `resolve_folder()` accepts any real directory on the machine.
_FOLDER_ALIASES = {
    "desktop": "Desktop",
    "schreibtisch": "Desktop",
    "documents": "Documents",
    "dokumente": "Documents",
    "downloads": "Downloads",
    "download": "Downloads",
    "pictures": "Pictures",
    "bilder": "Pictures",
    "music": "Music",
    "musik": "Music",
    "videos": "Videos",
    "movies": "Movies",
    "filme": "Movies",
    "home": "",
    "home folder": "",
    "benutzerordner": "",
}


def _normalize_spoken_target(name: str) -> str:
    normalized = re.sub(r"\s+", " ", name.casefold().strip().replace("-", " "))
    return normalized.strip(" \t\r\n.,!?;:'\"“”„")


def resolve_application_name(name: str) -> str | None:
    """Resolve a spoken application name to a catalogue identifier."""
    return _APP_ALIASES.get(_normalize_spoken_target(name))


def _application_search_roots() -> list[Path]:
    if sys.platform == "darwin":
        return [
            Path("/Applications"),
            Path("/Applications/Utilities"),
            Path("/System/Applications"),
            Path("/System/Applications/Utilities"),
            Path.home() / "Applications",
        ]
    if sys.platform == "win32":
        env = os.environ
        roots = [
            *(Path(value) for key in ("PROGRAMFILES", "PROGRAMFILES(X86)") if (value := env.get(key, ""))),
            *(Path(value, "Programs") for key in ("LOCALAPPDATA",) if (value := env.get(key, ""))),
            *(Path(value, "Microsoft/Windows/Start Menu/Programs") for key in ("APPDATA", "PROGRAMDATA") if (value := env.get(key, ""))),
        ]
        return [root for root in roots if root.is_dir()]
    return [
        Path("/usr/share/applications"),
        Path.home() / ".local/share/applications",
    ]


def _application_entries(root: Path, suffixes: set[str], limit: int = 5000) -> list[Path]:
    """List launchable entries without an unbounded Program Files walk."""
    if sys.platform != "win32":
        try:
            return [entry for entry in root.iterdir() if entry.suffix.lower() in suffixes]
        except OSError:
            return []

    lowered = str(root).casefold().replace("\\", "/")
    recursive = "/start menu/programs" in lowered or (
        bool(os.getenv("LOCALAPPDATA"))
        and root == Path(os.environ["LOCALAPPDATA"], "Programs")
    )
    if not recursive:
        try:
            return [entry for entry in root.iterdir() if entry.suffix.lower() in suffixes]
        except OSError:
            return []

    matches: list[Path] = []
    scanned = 0
    for directory, directories, filenames in os.walk(root):
        directories[:] = [name for name in directories if not name.startswith(".")]
        for filename in filenames:
            scanned += 1
            if Path(filename).suffix.lower() in suffixes:
                matches.append(Path(directory, filename))
            if scanned >= limit:
                return matches
    return matches


def find_installed_application(name: str) -> Path | None:
    """Find any application installed on this machine by its spoken name.

    The catalogue covers the common ones with tidy labels; this covers
    everything else the user actually has, so "open Blender" works without
    Blender ever having been listed anywhere.
    """
    wanted = _normalize_spoken_target(name)
    if not wanted:
        return None
    suffixes = {
        "darwin": {".app"},
        "win32": {".exe", ".lnk"},
    }.get(sys.platform, {".desktop"})

    exact: list[Path] = []
    partial: list[Path] = []
    for root in _application_search_roots():
        if not root.is_dir():
            continue
        entries = _application_entries(root, suffixes)
        for entry in entries:
            if entry.suffix.lower() not in suffixes:
                continue
            label = _normalize_spoken_target(entry.stem)
            if label == wanted:
                exact.append(entry)
            elif wanted in label or label in wanted:
                partial.append(entry)
    if exact:
        return exact[0]
    # Prefer the shortest partial match: "code" should find "Code", not
    # "Code Composer Studio".
    return min(partial, key=lambda path: len(path.stem)) if partial else None


def is_known_folder_name(name: str) -> bool:
    """Return whether the target is one of JARVIS's standard user folders."""
    return _normalize_spoken_target(name) in _FOLDER_ALIASES


def resolve_known_folder(name: str) -> Path | None:
    """Resolve one of the standard user folders."""
    normalized = _normalize_spoken_target(name)
    relative = _FOLDER_ALIASES.get(normalized)
    if relative is None:
        return None
    if sys.platform == "win32":
        path = _windows_known_folder(relative)
    elif sys.platform == "linux":
        path = _linux_known_folder(relative)
    else:
        path = Path.home() / relative if relative else Path.home()
    return path if path.exists() and path.is_dir() else None


def _windows_known_folder(relative: str) -> Path:
    """Resolve redirected Windows user folders, including OneDrive locations."""
    if not relative:
        return Path.home()
    windows_relative = "Videos" if relative == "Movies" else relative
    value_names = {
        "Desktop": "Desktop",
        "Documents": "Personal",
        "Downloads": "{374DE290-123F-4565-9164-39C4925E467B}",
        "Pictures": "My Pictures",
        "Music": "My Music",
        "Videos": "My Video",
    }
    value_name = value_names.get(windows_relative)
    if value_name:
        try:
            import winreg
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders",
            ) as key:
                raw, _ = winreg.QueryValueEx(key, value_name)
            resolved = Path(os.path.expandvars(str(raw))).expanduser()
            if resolved.is_dir():
                return resolved
        except (ImportError, OSError, ValueError):
            pass
    one_drive = os.getenv("OneDrive", "").strip()
    candidates = [
        Path(one_drive, windows_relative) if one_drive else None,
        Path.home() / windows_relative,
    ]
    return next((candidate for candidate in candidates if candidate and candidate.is_dir()), Path.home() / windows_relative)


def _linux_known_folder(relative: str) -> Path:
    """Honor localized XDG folders instead of assuming English directory names."""
    if not relative:
        return Path.home()
    linux_relative = "Videos" if relative == "Movies" else relative
    key = {
        "Desktop": "DESKTOP",
        "Documents": "DOCUMENTS",
        "Downloads": "DOWNLOAD",
        "Pictures": "PICTURES",
        "Music": "MUSIC",
        "Videos": "VIDEOS",
    }.get(linux_relative)
    executable = shutil.which("xdg-user-dir")
    if key and executable:
        try:
            result = subprocess.run(
                [executable, key],
                capture_output=True,
                text=True,
                timeout=2,
                check=False,
            ).stdout.strip()
            resolved = Path(result).expanduser()
            if result and resolved.is_dir():
                return resolved
        except (OSError, subprocess.SubprocessError):
            pass
    return Path.home() / linux_relative


def _expand_spoken_path(name: str) -> Path | None:
    """Turn spoken or typed text into a path, if it names one."""
    text = name.strip().strip("'\"“”„").rstrip(".,!?;:")
    if not text:
        return None
    # Spoken paths arrive with spaces around the separators often enough that
    # stripping them is worth it: "Documents / Steuern 2026".
    text = re.sub(r"\s*/\s*", "/", text)
    if not (text.startswith(("/", "~", ".")) or (len(text) > 2 and text[1] == ":")):
        return None
    try:
        return Path(text).expanduser()
    except (OSError, ValueError):
        return None


def find_folder(name: str, limit: int = 4000) -> Path | None:
    """Find any directory on the machine, by path or by name.

    Searched breadth-first from home so the answer is the closest match rather
    than whichever one a full-disk walk happens to reach first. Package
    contents and the caches nobody means are skipped.
    """
    direct = _expand_spoken_path(name)
    if direct is not None and direct.is_dir():
        return direct

    wanted = _normalize_spoken_target(name)
    if not wanted:
        return None

    skip_names = {"node_modules", "Library", ".git", ".venv", "__pycache__", "site-packages"}
    queue: list[Path] = [Path.home()]
    seen = 0
    partial: Path | None = None
    while queue and seen < limit:
        current = queue.pop(0)
        try:
            entries = sorted(current.iterdir())
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir() or entry.is_symlink():
                continue
            if entry.name in skip_names or entry.suffix in {".app", ".bundle", ".framework"}:
                continue
            seen += 1
            label = _normalize_spoken_target(entry.name)
            if label == wanted:
                return entry
            if partial is None and wanted in label:
                partial = entry
            if not entry.name.startswith("."):
                queue.append(entry)
    return partial


def resolve_folder(name: str) -> Path | None:
    """Resolve a spoken folder to any real directory on this machine."""
    return resolve_known_folder(name) or find_folder(name)


def _windows_program_candidates(app_id: str) -> list[Path]:
    env = os.environ
    program_files = [
        env.get("PROGRAMFILES", ""),
        env.get("PROGRAMFILES(X86)", ""),
        env.get("LOCALAPPDATA", ""),
        env.get("APPDATA", ""),
    ]
    relatives = {
        "chrome": [("Google", "Chrome", "Application", "chrome.exe")],
        "firefox": [("Mozilla Firefox", "firefox.exe")],
        "edge": [("Microsoft", "Edge", "Application", "msedge.exe")],
        "spotify": [("Spotify", "Spotify.exe")],
        "vscode": [("Programs", "Microsoft VS Code", "Code.exe"), ("Microsoft VS Code", "Code.exe")],
        "outlook": [
            ("Microsoft Office", "root", "Office16", "OUTLOOK.EXE"),
            ("Microsoft Office", "Office16", "OUTLOOK.EXE"),
        ],
    }
    return [Path(root, *relative) for root in program_files if root for relative in relatives.get(app_id, [])]


_WINDOWS_START_APP_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$OutputEncoding = [Console]::OutputEncoding = [Text.Encoding]::UTF8
$request = ([Console]::In.ReadToEnd() | ConvertFrom-Json)
$query = [string]$request.query
if ([string]::IsNullOrWhiteSpace($query)) { exit 2 }
$apps = @(Get-StartApps)
$match = $apps | Where-Object { $_.Name -eq $query } | Select-Object -First 1
if ($null -eq $match) {
    $match = $apps | Where-Object {
        $_.Name.IndexOf($query, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or
        $query.IndexOf($_.Name, [StringComparison]::OrdinalIgnoreCase) -ge 0
    } | Sort-Object { $_.Name.Length } | Select-Object -First 1
}
if ($null -eq $match) { exit 3 }
[PSCustomObject]@{ name = [string]$match.Name; app_id = [string]$match.AppID } |
    ConvertTo-Json -Compress
""".strip()


async def _find_windows_start_app(name: str) -> tuple[str, str] | None:
    """Resolve a Windows Start/Store app without putting user text in a script."""
    powershell = shutil.which("powershell.exe") or shutil.which("pwsh.exe") or shutil.which("pwsh")
    query = name.strip()
    if not powershell or not query:
        return None
    try:
        process = await asyncio.create_subprocess_exec(
            powershell,
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _WINDOWS_START_APP_SCRIPT,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(
            process.communicate(input=json.dumps({"query": query}).encode("utf-8")),
            timeout=8,
        )
        if process.returncode != 0 or not stdout.strip():
            return None
        payload = json.loads(stdout.decode("utf-8-sig"))
        label = str(payload.get("name", "")).strip()
        app_id = str(payload.get("app_id", "")).strip()
        if not label or not app_id or len(label) > 256 or len(app_id) > 512:
            return None
        if any(ord(character) < 32 for character in label + app_id):
            return None
        return label, app_id
    except (asyncio.TimeoutError, OSError, ValueError, TypeError):
        return None


async def _open_windows_start_app(*queries: str) -> dict:
    """Launch a Start-menu or Microsoft Store app through its OS-issued AppID."""
    for query in queries:
        match = await _find_windows_start_app(query)
        if match is None:
            continue
        label, app_id = match
        try:
            await asyncio.create_subprocess_exec(
                "explorer.exe",
                f"shell:AppsFolder\\{app_id}",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {"success": True, "confirmation": f"Opened {label}, sir."}
        except OSError as exc:
            log.warning("Could not launch Windows Start app %s: %s", label, exc)
    fallback = next((query.strip() for query in queries if query.strip()), "that application")
    return {"success": False, "confirmation": f"I couldn't find {fallback} on this PC, sir."}


async def _open_installed_application(name: str) -> dict:
    """Launch any application found on this machine, without a shell."""
    installed = find_installed_application(name)
    if installed is None:
        if sys.platform == "win32":
            return await _open_windows_start_app(name)
        return {"success": False, "confirmation": f"I couldn't find {name.strip()} on this computer, sir."}
    label = installed.stem
    if sys.platform == "darwin":
        command = ("/usr/bin/open", "-a", str(installed))
    elif sys.platform == "win32":
        try:
            os.startfile(str(installed))
            return {"success": True, "confirmation": f"Opened {label}, sir."}
        except OSError as exc:
            log.warning("Could not open %s on Windows: %s", label, exc)
            return {"success": False, "confirmation": f"I couldn't open {label}, sir."}
    else:
        gio = shutil.which("gio")
        gtk_launch = shutil.which("gtk-launch")
        xdg_open = shutil.which("xdg-open")
        if gio:
            command = (gio, "launch", str(installed))
        elif gtk_launch:
            command = (gtk_launch, installed.stem)
        elif xdg_open:
            command = (xdg_open, str(installed))
        else:
            return {"success": False, "confirmation": f"I couldn't launch {label}, sir."}
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()
    except OSError as exc:
        log.warning("Could not open %s: %s", label, exc)
        return {"success": False, "confirmation": f"I couldn't open {label}, sir."}
    if process.returncode != 0:
        log.info("Could not open %s: %s", label, stderr.decode(errors="replace").strip())
        return {"success": False, "confirmation": f"I couldn't open {label}, sir."}
    return {"success": True, "confirmation": f"Opened {label}, sir."}


async def open_application(name: str) -> dict:
    """Open a desktop application by name, without invoking a shell."""
    app_id = resolve_application_name(name)
    if not app_id:
        # Not one of the nicely-labelled common apps — look for it among
        # everything that is actually installed.
        return await _open_installed_application(name)
    label = _APP_LABELS[app_id]

    if sys.platform == "darwin":
        mac_apps = {
            "chrome": "Google Chrome",
            "safari": "Safari",
            "firefox": "Firefox",
            "edge": "Microsoft Edge",
            "mail": "Mail",
            "outlook": "Microsoft Outlook",
            "calendar": "Calendar",
            "notes": "Notes",
            "spotify": "Spotify",
            "music": "Music",
            "vscode": "Visual Studio Code",
            "files": "Finder",
            "settings": "System Settings",
            "calculator": "Calculator",
            "notepad": "TextEdit",
            "terminal": "Terminal",
            "task_manager": "Activity Monitor",
        }
        try:
            process = await asyncio.create_subprocess_exec(
                "/usr/bin/open", "-a", mac_apps[app_id],
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()
        except OSError as exc:
            log.warning("Could not open %s on macOS: %s", label, exc)
            return {"success": False, "confirmation": f"I couldn't open {label}, sir."}
        if process.returncode != 0:
            log.info("Could not open %s on macOS: %s", label, stderr.decode(errors="replace").strip())
            # The catalogue name may not be what it is called here — try what
            # the user actually said against what is installed.
            return await _open_installed_application(name)
        return {"success": True, "confirmation": f"Opened {label}, sir."}

    if sys.platform == "win32":
        fixed_commands = {
            "files": ("explorer.exe",),
            "settings": ("explorer.exe", "ms-settings:"),
            "calculator": ("calc.exe",),
            "notepad": ("notepad.exe",),
            "notes": ("notepad.exe",),
            "music": ("explorer.exe", "mswindowsmusic:"),
            "task_manager": ("taskmgr.exe",),
        }
        command = fixed_commands.get(app_id)
        if app_id == "terminal":
            terminal = shutil.which("wt.exe") or shutil.which("powershell.exe") or shutil.which("cmd.exe")
            command = (terminal,) if terminal else None
        if app_id in {"mail", "calendar"}:
            outlook = next((str(path) for path in _windows_program_candidates("outlook") if path.is_file()), "")
            if not outlook:
                outlook = shutil.which("OUTLOOK.EXE") or shutil.which("outlook.exe") or ""
            if outlook:
                folder = "outlook:inbox" if app_id == "mail" else "outlook:calendar"
                command = (outlook, "/select", folder)
        if not command:
            executable = next((str(path) for path in _windows_program_candidates(app_id) if path.is_file()), "")
            if not executable:
                executable = next(
                    (shutil.which(candidate) for candidate in {
                        "chrome": ("chrome.exe", "chrome"),
                        "firefox": ("firefox.exe", "firefox"),
                        "edge": ("msedge.exe", "msedge"),
                        "spotify": ("Spotify.exe", "spotify"),
                        "vscode": ("Code.exe", "code"),
                        "outlook": ("OUTLOOK.EXE", "outlook"),
                    }.get(app_id, ()) if shutil.which(candidate)),
                    "",
                )
            if executable:
                command = (executable,)
        if not command:
            start_queries = {
                "mail": ("Mail", "Outlook"),
                "calendar": ("Calendar", "Kalender", "Outlook"),
                "outlook": ("Outlook",),
                "safari": ("Safari",),
            }.get(app_id, (name, label))
            return await _open_windows_start_app(*start_queries)
        try:
            await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {"success": True, "confirmation": f"Opened {label}, sir."}
        except OSError as exc:
            log.warning("Could not open %s on Windows: %s", label, exc)
            return {"success": False, "confirmation": f"I couldn't open {label}, sir."}

    linux_commands = {
        "chrome": ("google-chrome", "chromium", "chromium-browser"),
        "firefox": ("firefox",),
        "edge": ("microsoft-edge",),
        "mail": ("thunderbird",),
        "calendar": ("gnome-calendar",),
        "notes": ("gnote",),
        "spotify": ("spotify",),
        "music": ("rhythmbox",),
        "vscode": ("code",),
        "calculator": ("gnome-calculator", "kcalc"),
        "notepad": ("gedit", "kate"),
        "terminal": ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm"),
        "task_manager": ("gnome-system-monitor", "plasma-systemmonitor", "ksysguard"),
    }
    if app_id == "files":
        return await open_known_folder("home")
    if app_id == "settings":
        settings = next(
            (
                shutil.which(candidate)
                for candidate in (
                    "gnome-control-center", "systemsettings6", "systemsettings5",
                    "systemsettings", "cinnamon-settings", "mate-control-center",
                    "xfce4-settings-manager",
                )
                if shutil.which(candidate)
            ),
            None,
        )
        if not settings:
            return {"success": False, "confirmation": "I couldn't find this desktop's System Settings, sir."}
        try:
            await asyncio.create_subprocess_exec(
                settings,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {"success": True, "confirmation": "Opened System Settings, sir."}
        except OSError as exc:
            log.warning("Could not open Linux System Settings: %s", exc)
            return {"success": False, "confirmation": "I couldn't open System Settings, sir."}
    executable = next((shutil.which(candidate) for candidate in linux_commands.get(app_id, ()) if shutil.which(candidate)), None)
    if not executable:
        return {"success": False, "confirmation": f"I couldn't find {label} on this computer, sir."}
    try:
        await asyncio.create_subprocess_exec(
            executable,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"success": True, "confirmation": f"Opened {label}, sir."}
    except OSError as exc:
        log.warning("Could not open %s on Linux: %s", label, exc)
        return {"success": False, "confirmation": f"I couldn't open {label}, sir."}


async def open_known_folder(name: str) -> dict:
    """Open any existing folder on this machine in the native file manager."""
    path = resolve_folder(name)
    if path is None:
        return {"success": False, "confirmation": f"I couldn't find a folder called {name.strip()}, sir."}
    if sys.platform == "darwin":
        command = ("/usr/bin/open", str(path))
        manager = "Finder"
    elif sys.platform == "win32":
        command = ("explorer.exe", str(path))
        manager = "File Explorer"
    else:
        opener = shutil.which("xdg-open")
        if not opener:
            return {"success": False, "confirmation": "I couldn't find a file manager, sir."}
        command = (opener, str(path))
        manager = "the file manager"
    try:
        await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        return {"success": True, "confirmation": f"Opened {path.name or 'Home'} in {manager}, sir."}
    except OSError as exc:
        log.warning("Could not open folder %s: %s", path, exc)
        return {"success": False, "confirmation": f"I couldn't open {path.name or 'Home'}, sir."}


_FILE_SEARCH_SKIP = {
    "node_modules", ".git", ".venv", "__pycache__", "site-packages",
    "Library", "AppData", "$Recycle.Bin", "System Volume Information",
}


def find_files(query: str, limit: int = 8, scan_limit: int = 50_000) -> list[Path]:
    """Find files anywhere in the user's home by name.

    Spotlight answers instantly and already indexes the whole home directory,
    so it is used where it exists; the walk is only the fallback for machines
    where indexing is off.
    """
    wanted = query.strip()
    if not wanted:
        return []

    direct = _expand_spoken_path(wanted)
    if direct is not None and direct.is_file():
        return [direct]

    if sys.platform == "darwin" and shutil.which("mdfind"):
        try:
            found = subprocess.run(
                ["mdfind", "-onlyin", str(Path.home()), "-name", wanted],
                capture_output=True, text=True, timeout=10, check=False,
            ).stdout.splitlines()
        except (OSError, subprocess.SubprocessError):
            found = []
        matches = [Path(line) for line in found if line]
        matches = [path for path in matches if path.is_file() and path.suffix != ".app"]
        if matches:
            return matches[:limit]

    normalized = _normalize_spoken_target(wanted)
    results: list[Path] = []
    scanned = 0
    for root, directories, filenames in os.walk(Path.home()):
        directories[:] = [name for name in directories if name not in _FILE_SEARCH_SKIP and not name.startswith(".")]
        for filename in filenames:
            scanned += 1
            if normalized in _normalize_spoken_target(filename):
                results.append(Path(root, filename))
                if len(results) >= limit:
                    return results
            if scanned >= scan_limit:
                return results
    return results


async def open_path(target: str) -> dict:
    """Open any file or folder with whatever application handles it."""
    path = _expand_spoken_path(target)
    if path is None or not path.exists():
        matches = find_files(target, limit=1)
        folder = None if matches else resolve_folder(target)
        path = matches[0] if matches else folder
    if path is None or not path.exists():
        return {"success": False, "confirmation": f"I couldn't find {target.strip()} on this computer, sir."}
    if path.is_dir():
        return await open_known_folder(str(path))
    if sys.platform == "win32":
        try:
            os.startfile(str(path))
        except OSError as exc:
            log.warning("Could not open %s on Windows: %s", path, exc)
            return {"success": False, "confirmation": f"I couldn't open {path.name}, sir."}
        return {"success": True, "confirmation": f"Opened {path.name}, sir."}
    if sys.platform == "darwin":
        command = ("/usr/bin/open", str(path))
    else:
        opener = shutil.which("xdg-open")
        if not opener:
            return {"success": False, "confirmation": "I couldn't find an application to open that, sir."}
        command = (opener, str(path))
    try:
        await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
    except OSError as exc:
        log.warning("Could not open %s: %s", path, exc)
        return {"success": False, "confirmation": f"I couldn't open {path.name}, sir."}
    return {"success": True, "confirmation": f"Opened {path.name}, sir."}


def _escape_applescript(s: str) -> str:
    """Escape a string for safe inclusion in an AppleScript double-quoted string.

    Handles backslashes, double quotes, and other special chars to prevent
    AppleScript injection from user-controlled input (e.g. voice transcription).
    """
    return s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "").replace("\r", "")


async def _mark_terminal_as_jarvis(revert_after: float = 5.0):
    """Temporarily set the front Terminal window to Ocean theme, then revert.

    Shows the user JARVIS is active in that terminal. Reverts after revert_after seconds.
    """
    # Save the current profile, switch to Ocean, then revert
    script_save = (
        'tell application "Terminal"\n'
        '    return name of current settings of front window\n'
        'end tell'
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script_save,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        original_profile = stdout.decode().strip()

        # Switch to Ocean
        script_set = (
            'tell application "Terminal"\n'
            '    set current settings of front window to settings set "Ocean"\n'
            'end tell'
        )
        proc2 = await asyncio.create_subprocess_exec(
            "osascript", "-e", script_set,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc2.communicate()

        # Schedule revert
        if original_profile and original_profile != "Ocean":
            asyncio.get_event_loop().call_later(
                revert_after,
                lambda: asyncio.ensure_future(_revert_terminal_theme(original_profile))
            )
    except Exception:
        pass


async def _revert_terminal_theme(profile_name: str):
    """Revert a Terminal window back to its original profile."""
    escaped = profile_name.replace('"', '\\"')
    script = (
        'tell application "Terminal"\n'
        f'    set current settings of front window to settings set "{escaped}"\n'
        'end tell'
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        await proc.communicate()
    except Exception:
        pass


async def open_terminal(command: str = "") -> dict:
    """Open the native platform terminal and optionally run a command."""
    # Voice actions only need a plain terminal or the fixed Claude launcher.
    # Keeping this an allow-list prevents transcribed text from becoming a shell
    # program if a future caller accidentally forwards it here.
    if command not in {"", "claude"}:
        return {"success": False, "confirmation": "I can't run arbitrary terminal commands from a voice action, sir."}
    if sys.platform == "win32":
        terminal = shutil.which("wt.exe") or shutil.which("powershell.exe") or shutil.which("cmd.exe")
        if not terminal:
            return {"success": False, "confirmation": "I couldn't find Windows Terminal, sir."}
        args: list[str] = []
        if command:
            if terminal.lower().endswith("wt.exe"):
                args = ["powershell.exe", "-NoExit", "-Command", command]
            elif terminal.lower().endswith("powershell.exe"):
                args = ["-NoExit", "-Command", command]
            else:
                args = ["/K", command]
        try:
            await asyncio.create_subprocess_exec(
                terminal,
                *args,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {"success": True, "confirmation": "Terminal is open, sir."}
        except OSError as exc:
            log.error("open_terminal (Windows) failed: %s", exc)
            return {"success": False, "confirmation": "I had trouble opening Terminal, sir."}

    if sys.platform != "darwin":
        terminal = next((shutil.which(name) for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm") if shutil.which(name)), None)
        if not terminal:
            return {"success": False, "confirmation": "I couldn't find a terminal application, sir."}
        args = ["-e", command] if command else []
        try:
            await asyncio.create_subprocess_exec(terminal, *args)
            return {"success": True, "confirmation": "Terminal is open, sir."}
        except OSError as exc:
            log.error("open_terminal (Linux) failed: %s", exc)
            return {"success": False, "confirmation": "I had trouble opening Terminal, sir."}

    if command:
        escaped = _escape_applescript(command)
        script = (
            'tell application "Terminal"\n'
            "    activate\n"
            f'    do script "{escaped}"\n'
            "end tell"
        )
    else:
        script = (
            'tell application "Terminal"\n'
            "    activate\n"
            "end tell"
        )
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    success = proc.returncode == 0
    if not success:
        log.error(f"open_terminal failed: {stderr.decode()}")
    else:
        await _mark_terminal_as_jarvis()
    return {
        "success": success,
        "confirmation": "Terminal is open, sir." if success else "I had trouble opening Terminal, sir.",
    }


async def open_browser(url: str, browser: str = "chrome") -> dict:
    """Open URL in user's browser (Chrome or Firefox)."""
    if not re.match(r"^(?:https?|file)://", url, flags=re.IGNORECASE):
        return {"success": False, "confirmation": "That address is not safe to open, sir."}

    if sys.platform == "win32":
        env = os.environ
        roots = [env.get("PROGRAMFILES", ""), env.get("PROGRAMFILES(X86)", ""), env.get("LOCALAPPDATA", "")]
        relative = (
            ("Mozilla Firefox", "firefox.exe")
            if browser.lower() == "firefox"
            else ("Google", "Chrome", "Application", "chrome.exe")
        )
        executable = next(
            (str(Path(root, *relative)) for root in roots if root and Path(root, *relative).is_file()),
            "",
        )
        app_name = "Firefox" if browser.lower() == "firefox" else "Chrome"
        try:
            if executable:
                await asyncio.create_subprocess_exec(
                    executable,
                    url,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            elif hasattr(os, "startfile"):
                await asyncio.to_thread(os.startfile, url)  # type: ignore[attr-defined]
                app_name = "your default browser"
            else:
                raise OSError("No Windows URL launcher is available")
            return {"success": True, "confirmation": f"Opened that in {app_name}, sir."}
        except OSError as exc:
            log.error("open_browser (Windows) failed: %s", exc)
            return {"success": False, "confirmation": "I had trouble opening the browser, sir."}

    if sys.platform != "darwin":
        opener = shutil.which("xdg-open")
        if not opener:
            return {"success": False, "confirmation": "I couldn't find a browser launcher, sir."}
        try:
            await asyncio.create_subprocess_exec(
                opener,
                url,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {"success": True, "confirmation": "Opened that in your browser, sir."}
        except OSError as exc:
            log.error("open_browser (Linux) failed: %s", exc)
            return {"success": False, "confirmation": "I had trouble opening the browser, sir."}

    escaped_url = _escape_applescript(url)

    if browser.lower() == "firefox":
        app_name = "Firefox"
        script = (
            'tell application "Firefox"\n'
            "    activate\n"
            f'    open location "{escaped_url}"\n'
            "end tell"
        )
    else:
        app_name = "Chrome"
        script = (
            'tell application "Google Chrome"\n'
            "    activate\n"
            f'    open location "{escaped_url}"\n'
            "end tell"
        )

    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    success = proc.returncode == 0
    if not success:
        log.error(f"open_browser ({app_name}) failed: {stderr.decode()}")
    return {
        "success": success,
        "confirmation": f"Pulled that up in {app_name}, sir." if success else f"{app_name} ran into a problem, sir.",
    }


# Keep backward compat
async def open_chrome(url: str) -> dict:
    return await open_browser(url, "chrome")


async def open_claude_in_project(project_dir: str, prompt: str, *, prepare_task: bool = True) -> dict:
    """Open Terminal, cd to project dir, run Claude Code interactively.

    Writes the prompt to CLAUDE.md (which claude reads automatically on startup)
    then launches claude in interactive mode.
    No prompt escaping needed — CLAUDE.md handles context delivery.
    """
    # New build sessions get their task through CLAUDE.md. Existing projects
    # opened from developer work mode must keep their own instructions intact.
    if prepare_task:
        claude_md = Path(project_dir) / "CLAUDE.md"
        claude_md.write_text(
            f"# Task\n\n{prompt}\n\nBuild this completely. If web app, make index.html work standalone.\n",
            encoding="utf-8",
        )

    if sys.platform == "win32":
        terminal = shutil.which("wt.exe") or shutil.which("powershell.exe") or shutil.which("cmd.exe")
        if not terminal:
            return {"success": False, "confirmation": "I couldn't find Windows Terminal, PowerShell, or Command Prompt, sir."}
        lowered = terminal.lower()
        if lowered.endswith("wt.exe"):
            args = ["-d", project_dir, "powershell.exe", "-NoExit", "-Command", "claude"]
        elif lowered.endswith("powershell.exe"):
            args = ["-NoExit", "-Command", "claude"]
        else:
            args = ["/K", "claude"]
        try:
            await asyncio.create_subprocess_exec(
                terminal,
                *args,
                cwd=project_dir,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            return {
                "success": True,
                "confirmation": "Claude Code is running in the project terminal, sir. You can watch the progress.",
            }
        except OSError as exc:
            log.error("open_claude_in_project (Windows) failed: %s", exc)
            return {"success": False, "confirmation": "Had trouble starting Claude Code in that project, sir."}

    if sys.platform != "darwin":
        terminal = next(
            (shutil.which(name) for name in ("x-terminal-emulator", "gnome-terminal", "konsole", "xterm") if shutil.which(name)),
            None,
        )
        shell = shutil.which("bash") or shutil.which("sh")
        if not terminal or not shell:
            return {"success": False, "confirmation": "I couldn't find a compatible terminal and shell, sir."}
        try:
            terminal_name = Path(terminal).name
            prefix = ["--"] if terminal_name == "gnome-terminal" else ["-e"]
            await asyncio.create_subprocess_exec(
                terminal,
                *prefix,
                shell,
                "-lc",
                'cd -- "$1" && exec claude',
                "jarvis",
                project_dir,
            )
            return {
                "success": True,
                "confirmation": "Claude Code is running in the project terminal, sir. You can watch the progress.",
            }
        except OSError as exc:
            log.error("open_claude_in_project (Linux) failed: %s", exc)
            return {"success": False, "confirmation": "Had trouble starting Claude Code in that project, sir."}

    # Launch claude interactive — it reads CLAUDE.md on its own
    script = """
on run argv
    set projectDirectory to item 1 of argv
    tell application "Terminal"
        activate
        do script "cd " & quoted form of projectDirectory & " && claude"
    end tell
end run
"""
    proc = await asyncio.create_subprocess_exec(
        "osascript", "-e", script, project_dir,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()
    success = proc.returncode == 0
    if not success:
        log.error(f"open_claude_in_project failed: {stderr.decode()}")
    else:
        await _mark_terminal_as_jarvis()
    return {
        "success": success,
        "confirmation": "Claude Code is running in Terminal, sir. You can watch the progress."
        if success
        else "Had trouble spawning Claude Code, sir.",
    }


async def prompt_existing_terminal(project_name: str, prompt: str) -> dict:
    """Find a Terminal window matching a project name and type a prompt into it.

    Uses System Events keystroke to type into an active Claude Code session
    rather than `do script` which would open a new shell.
    """
    if sys.platform != "darwin":
        return {
            "success": False,
            "confirmation": "Reusing an existing interactive terminal is currently available only on macOS, sir. I can open a new project terminal instead.",
        }

    escaped_name = _escape_applescript(project_name)
    escaped_prompt = _escape_applescript(prompt)

    # Single atomic script: find window, focus it, type into it
    script = f'''
tell application "Terminal"
    set matched to false
    set targetWindow to missing value
    repeat with w in windows
        if name of w contains "{escaped_name}" then
            set targetWindow to w
            set matched to true
            exit repeat
        end if
    end repeat

    if not matched then
        return "NOT_FOUND"
    end if

    -- Bring the matched window to front
    set index of targetWindow to 1
    set selected tab of targetWindow to selected tab of targetWindow
    activate
end tell

-- Wait for window to be fully focused
delay 1

-- Now type into it
tell application "System Events"
    tell process "Terminal"
        set frontmost to true
        delay 0.3
        keystroke "{escaped_prompt}"
        delay 0.2
        keystroke return
    end tell
end tell

return "OK"
'''

    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=15)

        result = stdout.decode().strip()
        if result == "NOT_FOUND":
            return {
                "success": False,
                "confirmation": f"Couldn't find a terminal for {project_name}, sir.",
            }

        success = proc.returncode == 0
        if not success:
            log.error(f"prompt_existing_terminal failed: {stderr.decode()[:200]}")

        if success:
            await _mark_terminal_as_jarvis()

        return {
            "success": success,
            "confirmation": f"Sent that to {project_name}, sir." if success
            else f"Had trouble typing into {project_name}, sir.",
        }

    except asyncio.TimeoutError:
        return {"success": False, "confirmation": "Terminal operation timed out, sir."}
    except Exception as e:
        log.error(f"prompt_existing_terminal failed: {e}")
        return {"success": False, "confirmation": "Something went wrong reaching that terminal, sir."}


async def get_chrome_tab_info() -> dict:
    """Read the current Chrome tab's title and URL via AppleScript."""
    if sys.platform != "darwin":
        return {}
    script = (
        'tell application "Google Chrome"\n'
        "    set tabTitle to title of active tab of front window\n"
        "    set tabURL to URL of active tab of front window\n"
        '    return tabTitle & "|" & tabURL\n'
        "end tell"
    )
    try:
        proc = await asyncio.create_subprocess_exec(
            "osascript", "-e", script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate()
        if proc.returncode == 0:
            result = stdout.decode().strip()
            parts = result.split("|", 1)
            if len(parts) == 2:
                return {"title": parts[0], "url": parts[1]}
        return {}
    except Exception as e:
        log.warning(f"get_chrome_tab_info failed: {e}")
        return {}


async def monitor_build(project_dir: str, ws=None, synthesize_fn=None) -> None:
    """Monitor a Claude Code build for completion. Notify via WebSocket when done."""
    import base64

    output_file = Path(project_dir) / ".jarvis_output.txt"
    start = time.time()
    timeout = 600  # 10 minutes

    while time.time() - start < timeout:
        await asyncio.sleep(5)
        if output_file.exists():
            content = output_file.read_text()
            if "--- JARVIS TASK COMPLETE ---" in content:
                log.info(f"Build complete in {project_dir}")
                if ws and synthesize_fn:
                    try:
                        msg = "The build is complete, sir."
                        audio_bytes = await synthesize_fn(msg)
                        if audio_bytes:
                            encoded = base64.b64encode(audio_bytes).decode()
                            await ws.send_json({"type": "status", "state": "speaking"})
                            await ws.send_json({"type": "audio", "data": encoded, "text": msg})
                            await ws.send_json({"type": "status", "state": "idle"})
                    except Exception as e:
                        log.warning(f"Build notification failed: {e}")
                return

    log.warning(f"Build timed out in {project_dir}")


async def execute_action(intent: dict, projects: list = None) -> dict:
    """Route a classified intent to the right action function.

    Args:
        intent: {"action": str, "target": str} from classify_intent()
        projects: list of known project dicts for resolving working dirs

    Returns: {"success": bool, "confirmation": str, "project_dir": str | None}
    """
    action = intent.get("action", "chat")
    target = intent.get("target", "")

    if action == "open_terminal":
        result = await open_terminal("claude")
        result["project_dir"] = None
        return result

    elif action == "browse":
        if target.startswith("http://") or target.startswith("https://"):
            url = target
        else:
            url = f"https://www.google.com/search?q={quote(target)}"

        # Detect which browser user wants
        target_lower = target.lower()
        if "firefox" in target_lower:
            browser = "firefox"
        else:
            browser = "chrome"

        result = await open_browser(url, browser)
        result["project_dir"] = None
        return result

    elif action == "build":
        # Create project folder on Desktop, spawn Claude Code
        project_name = _generate_project_name(target)
        desktop = resolve_known_folder("desktop") or DESKTOP_PATH
        project_dir = str(desktop / project_name)
        os.makedirs(project_dir, exist_ok=True)
        result = await open_claude_in_project(project_dir, target)
        result["project_dir"] = project_dir
        return result

    else:
        return {"success": False, "confirmation": "", "project_dir": None}


def _generate_project_name(prompt: str) -> str:
    """Generate a kebab-case project folder name from the prompt."""
    # First: check for a quoted name like "tiktok-analytics-dashboard"
    quoted = re.search(r'"([^"]+)"', prompt)
    if quoted:
        name = quoted.group(1).strip()
        # Already kebab-case or close to it
        name = re.sub(r"[^a-zA-Z0-9\s-]", "", name).strip()
        if name:
            return re.sub(r"[\s]+", "-", name.lower())

    # Second: check for "called X" or "named X" pattern
    called = re.search(r'(?:called|named)\s+(\S+(?:[-_]\S+)*)', prompt, re.IGNORECASE)
    if called:
        name = re.sub(r"[^a-zA-Z0-9-]", "", called.group(1))
        if len(name) > 3:
            return name.lower()

    # Fallback: extract meaningful words
    words = re.sub(r"[^a-zA-Z0-9\s]", "", prompt.lower()).split()
    skip = {"a", "the", "an", "me", "build", "create", "make", "for", "with", "and",
            "to", "of", "i", "want", "need", "new", "project", "directory", "called",
            "on", "desktop", "that", "application", "app", "full", "stack", "simple",
            "web", "page", "site", "named"}
    meaningful = [w for w in words if w not in skip and len(w) > 2][:4]
    return "-".join(meaningful) if meaningful else "jarvis-project"
