"""Build the pinned, offline whisper.cpp runtime included with desktop releases."""

from __future__ import annotations

import hashlib
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "desktop" / "speech-runtime"
CACHE = ROOT / "build" / "speech-cache"
VERSION = "1.8.6"
SOURCE_URL = f"https://github.com/ggml-org/whisper.cpp/archive/refs/tags/v{VERSION}.tar.gz"
SOURCE_SHA256 = "f8e632016ceae556f3132a16c7f704be1e7715595041f474fa81a2b64c1abf7c"
MODEL_NAME = "ggml-large-v3-turbo-q8_0.bin"
MODEL_URL = f"https://huggingface.co/ggerganov/whisper.cpp/resolve/5359861c739e955e79d9a303bcbc70fb988958b1/{MODEL_NAME}"
MODEL_SHA256 = "317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, destination: Path, expected: str) -> None:
    if destination.is_file() and sha256(destination) == expected:
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    # A developer can trigger packaging from two terminals. Unique temporary
    # names avoid one build deleting or renaming another build's download.
    partial = destination.with_suffix(destination.suffix + f".partial.{os.getpid()}")
    partial.unlink(missing_ok=True)
    print(f"Downloading {destination.name}…")
    request = urllib.request.Request(url, headers={"User-Agent": "JARVIS-v4-release-builder"})
    with urllib.request.urlopen(request, timeout=120) as response, partial.open("wb") as output:
        shutil.copyfileobj(response, output, length=1024 * 1024)
    actual = sha256(partial)
    if actual != expected:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"Checksum mismatch for {destination.name}: {actual}")
    partial.replace(destination)


def safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with tarfile.open(archive, "r:gz") as bundle:
        for member in bundle.getmembers():
            target = (destination / member.name).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError("Unsafe path in whisper.cpp source archive")
        bundle.extractall(destination)


def locate_binary(build_dir: Path) -> Path:
    name = "whisper-server.exe" if os.name == "nt" else "whisper-server"
    candidates = [
        build_dir / "bin" / "Release" / name,
        build_dir / "bin" / name,
        build_dir / "examples" / "server" / "Release" / name,
        build_dir / "examples" / "server" / name,
    ]
    match = next((candidate for candidate in candidates if candidate.is_file()), None)
    if not match:
        raise RuntimeError(f"whisper.cpp built successfully but {name} was not found")
    return match


def build_runtime() -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    archive = CACHE / f"whisper.cpp-v{VERSION}.tar.gz"
    download(SOURCE_URL, archive, SOURCE_SHA256)
    machine = platform.machine().lower().replace("amd64", "x86_64")
    workspace = ROOT / "build" / f"whisper.cpp-{VERSION}-{sys.platform}-{machine}"
    source = workspace / f"whisper.cpp-{VERSION}"
    build_dir = workspace / "cmake-build"
    if not source.is_dir():
        shutil.rmtree(workspace, ignore_errors=True)
        safe_extract(archive, workspace)
    command = [
        "cmake", "-S", str(source), "-B", str(build_dir),
        "-DWHISPER_BUILD_TESTS=OFF",
        "-DWHISPER_BUILD_EXAMPLES=ON",
        "-DWHISPER_SDL2=OFF",
        "-DBUILD_SHARED_LIBS=OFF",
        "-DGGML_NATIVE=OFF",
        "-DCMAKE_BUILD_TYPE=Release",
    ]
    subprocess.run(command, check=True)
    subprocess.run(
        ["cmake", "--build", str(build_dir), "--config", "Release", "--target", "whisper-server", "--parallel", "2"],
        check=True,
    )
    return locate_binary(build_dir)


def main() -> int:
    if not shutil.which("cmake"):
        print("CMake is required to build bundled offline speech recognition.", file=sys.stderr)
        return 2
    executable = build_runtime()
    model_cache = CACHE / MODEL_NAME
    if not model_cache.exists():
        reusable_models = [
            ROOT / "build" / "speech-model-upgrade" / MODEL_NAME,
            Path.home() / ".whisper-models" / MODEL_NAME,
            OUTPUT / MODEL_NAME,
        ]
        reusable = next((path for path in reusable_models if path.is_file() and sha256(path) == MODEL_SHA256), None)
        if reusable:
            model_cache.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(reusable, model_cache)
    download(MODEL_URL, model_cache, MODEL_SHA256)

    OUTPUT.mkdir(parents=True, exist_ok=True)
    output_name = "whisper-server.exe" if os.name == "nt" else "whisper-server"
    shutil.copy2(executable, OUTPUT / output_name)
    shutil.copy2(model_cache, OUTPUT / MODEL_NAME)
    # Keep the release to one recognition model. Q8 preserves far more weight
    # precision than the old Q5 pack while Turbo's distilled decoder keeps a
    # spoken command responsive within the shared 2.5 GiB desktop budget on
    # supported Windows, macOS and Linux machines.
    for superseded in (
        "ggml-large-v3-q5_0.bin",
        "ggml-large-v3-turbo-q5_0.bin",
        "ggml-base.bin",
        "ggml-small-q8_0.bin",
        "ggml-small.bin",
    ):
        (OUTPUT / superseded).unlink(missing_ok=True)
    source_license = ROOT / "build" / f"whisper.cpp-{VERSION}-{sys.platform}-{platform.machine().lower().replace('amd64', 'x86_64')}" / f"whisper.cpp-{VERSION}" / "LICENSE"
    shutil.copy2(source_license, OUTPUT / "WHISPER_CPP_LICENSE.txt")
    (OUTPUT / "RUNTIME.txt").write_text(
        f"whisper.cpp v{VERSION}\nmodel: {MODEL_NAME}\nmodel sha256: {MODEL_SHA256}\n",
        encoding="utf-8",
    )
    if os.name != "nt":
        (OUTPUT / output_name).chmod(0o755)
    print(f"Offline speech runtime ready at {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
