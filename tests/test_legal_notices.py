from pathlib import Path

from scripts import collect_legal_notices
from scripts.collect_legal_notices import canonical, license_candidates, locked_python_names


def test_locked_python_names_preserve_every_exact_release_component(tmp_path: Path):
    lockfile = tmp_path / "requirements.lock"
    lockfile.write_text(
        "FastAPI==1.2.3 \\\n  --hash=sha256:abc\n"
        "pywin32-ctypes==0.2.3 ; sys_platform == 'win32' \\\n  --hash=sha256:def\n",
        encoding="utf-8",
    )

    assert locked_python_names(lockfile) == {"fastapi", "pywin32-ctypes"}


def test_license_candidates_accept_common_notice_names_only():
    candidates = license_candidates(
        [
            Path("package/LICENSE"),
            Path("dist-info/licenses/COPYING.txt"),
            Path("NOTICE.md"),
            Path("source.py"),
        ]
    )

    assert candidates == [
        Path("package/LICENSE"),
        Path("dist-info/licenses/COPYING.txt"),
        Path("NOTICE.md"),
    ]


def test_canonical_normalizes_python_and_npm_names():
    assert canonical("typing_extensions") == "typing-extensions"
    assert canonical("@Types.Node") == "@types-node"


def test_npm_license_scan_uses_the_windows_command_shim(monkeypatch, tmp_path: Path):
    calls: list[tuple[list[str], Path]] = []

    class Completed:
        stdout = f"{tmp_path}\n{tmp_path / 'node_modules' / 'three'}\n"

    monkeypatch.setattr(
        collect_legal_notices.shutil,
        "which",
        lambda name: r"C:\Program Files\nodejs\npm.cmd" if name == "npm.cmd" else None,
    )

    def run(command, *, cwd, **_kwargs):
        calls.append((command, cwd))
        return Completed()

    monkeypatch.setattr(collect_legal_notices.subprocess, "run", run)

    assert collect_legal_notices.npm_package_paths(tmp_path) == [
        tmp_path / "node_modules" / "three"
    ]
    assert calls == [
        ([r"C:\Program Files\nodejs\npm.cmd", "ls", "--omit=dev", "--all", "--parseable"], tmp_path)
    ]
