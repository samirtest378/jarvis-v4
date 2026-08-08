"""Create the platform-specific Python sidecar used by Electron."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from collect_legal_notices import main as collect_legal_notices


ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "desktop" / "dist-backend"
BUILD = ROOT / "build" / "pyinstaller"


def main() -> int:
    if sys.version_info < (3, 11):
        print("Python 3.11 or newer is required to package JARVIS.", file=sys.stderr)
        return 2
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print(
            "PyInstaller is missing. Install the verified requirements-build.lock.txt first.",
            file=sys.stderr,
        )
        return 2

    frontend = ROOT / "frontend" / "dist"
    if not (frontend / "index.html").exists():
        print("frontend/dist is missing; run the frontend build first.", file=sys.stderr)
        return 2

    shutil.rmtree(DIST, ignore_errors=True)
    DIST.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    separator = os.pathsep
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        # A one-file build re-extracts its whole ~21 MB payload into a temp
        # directory on *every* launch, which measured 9.8 s of the app's start.
        # A directory build simply runs, at the cost of shipping a folder.
        "--onedir",
        "--contents-directory",
        "_internal",
        "--name",
        "jarvis-server",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        "--add-data",
        f"{frontend}{separator}frontend/dist",
        "--add-data",
        f"{ROOT / 'templates'}{separator}templates",
        "--add-data",
        f"{ROOT / '.env.example'}{separator}.",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        str(ROOT / "server.py"),
    ]
    subprocess.run(command, cwd=ROOT, check=True)
    collect_legal_notices()
    print(f"Backend sidecar created at {DIST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
