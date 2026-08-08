"""Build an optional, self-contained JARVIS v4 offline voice pack."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
import sysconfig
import zipfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "build" / "local-voice"
TURBO_MODEL_FILES = (
    "t3_turbo_v1.safetensors",
    "s3gen_meanflow.safetensors",
    "ve.safetensors",
    "conds.pt",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "added_tokens.json",
    "vocab.json",
    "merges.txt",
)

MULTILINGUAL_MODEL_FILES = (
    "ve.pt",
    "t3_mtl23ls_v2.safetensors",
    "s3gen.pt",
    "grapheme_mtl_merged_expanded_v1.json",
    "conds.pt",
)

MOSS_TTS_MODEL_FILES = (
    "config.json",
    "model.safetensors",
    "special_tokens_map.json",
    "tokenizer.model",
    "tokenizer_config.json",
)

MOSS_AUDIO_TOKENIZER_FILES = (
    "config.json",
    "model-00001-of-00001.safetensors",
    "model.safetensors.index.json",
)

NEUTTS_MODEL_FILES = (
    "neutts-nano-german-Q4_0.gguf",
    "neutts-nano-Q4_0.gguf",
    "neucodec-int8.onnx",
    "NEUTTS_MODEL_LICENSE.txt",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _voice_site_packages(python: Path) -> Path:
    code = "import json,sysconfig;print(json.dumps(sysconfig.get_paths()))"
    result = subprocess.run([str(python), "-c", code], check=True, capture_output=True, text=True)
    paths = json.loads(result.stdout)
    return Path(paths["purelib"])


def _onnx_distribution_name() -> str:
    """Return the installed CPU/GPU distribution name for PyInstaller."""
    for name in ("onnxruntime-gpu", "onnxruntime"):
        try:
            importlib.metadata.distribution(name)
            return name
        except importlib.metadata.PackageNotFoundError:
            continue
    raise RuntimeError("ONNX Runtime is not installed")


def _copy_licenses(site_packages: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for dist_info in sorted(site_packages.glob("*.dist-info")):
        candidates = list((dist_info / "licenses").glob("**/*")) if (dist_info / "licenses").is_dir() else []
        candidates.extend(path for path in dist_info.glob("LICENSE*") if path.is_file())
        files = [path for path in candidates if path.is_file()]
        if not files:
            continue
        package_target = target / dist_info.name.removesuffix(".dist-info")
        package_target.mkdir(parents=True, exist_ok=True)
        for index, source in enumerate(files):
            name = source.name if not (package_target / source.name).exists() else f"{index}-{source.name}"
            shutil.copy2(source, package_target / name)


def _build_engine(python: Path, distribution: Path, mode: str) -> Path:
    shutil.rmtree(distribution, ignore_errors=True)
    work = BUILD / "pyinstaller-work"
    spec = BUILD / "pyinstaller-spec"
    command = [
        str(python), "-m", "PyInstaller",
        "--noconfirm", "--clean", "--onedir",
        "--name", "jarvis-voice-engine",
        "--distpath", str(distribution),
        "--workpath", str(work),
        "--specpath", str(spec),
    ]
    if mode == "neutts-nano":
        onnx_distribution = _onnx_distribution_name()
        command.extend([
            # The JARVIS runtime uses only the quantized llama.cpp backbone,
            # the ONNX decoder and a minimal eSpeak binding. Reference encoding,
            # training, PyTorch and Transformers are intentionally excluded.
            "--collect-binaries", "llama_cpp",
            # The contributed PyInstaller hook already follows ONNX Runtime's
            # required shared libraries. Collecting the whole package also
            # bundled conversion CLIs, quantizers, benchmarks and transformer
            # tooling that the compact decoder can never import.
            "--collect-binaries", "onnxruntime",
            "--exclude-module", "torch",
            "--exclude-module", "torchaudio",
            "--exclude-module", "transformers",
            "--exclude-module", "neutts",
            "--exclude-module", "neucodec",
            "--exclude-module", "librosa",
            "--exclude-module", "scipy",
            "--exclude-module", "perth",
            "--exclude-module", "pandas",
            "--exclude-module", "pyarrow",
            "--exclude-module", "numba",
            "--exclude-module", "rdflib",
            "--copy-metadata", "llama-cpp-python",
            "--copy-metadata", onnx_distribution,
            str(ROOT / "local_voice" / "neutts_engine.py"),
        ])
    elif mode == "moss-nano":
        moss_codec_source = (
            _voice_site_packages(python)
            / "mlx_audio"
            / "codec"
            / "models"
            / "moss_audio_tokenizer"
            / "moss_audio_tokenizer.py"
        )
        sample_utils_source = _voice_site_packages(python) / "mlx_lm" / "sample_utils.py"
        for runtime_source in (moss_codec_source, sample_utils_source):
            if not runtime_source.is_file():
                raise FileNotFoundError(f"MLX voice runtime source is missing: {runtime_source}")
        command.extend([
            "--runtime-hook", str(ROOT / "local_voice" / "mlx_frozen_runtime.py"),
            # `collect-all mlx_audio/transformers` used to pull every speech,
            # music, vision and test model into a one-purpose TTS helper. That
            # added hundreds of megabytes and ~20 seconds of frozen startup.
            # MOSS Nano loads its architecture dynamically, so declare only
            # the two runtime model families it actually needs.
            "--hidden-import", "mlx_audio.tts.models.moss_tts_nano",
            "--add-data", f"{moss_codec_source}:_jarvis_voice",
            "--add-data", f"{sample_utils_source}:_jarvis_voice",
            "--exclude-module", "mlx_audio.codec",
            "--exclude-module", "mlx_lm",
            "--exclude-module", "transformers",
            "--exclude-module", "scipy",
            "--collect-all", "mlx",
            "--collect-all", "sentencepiece",
            "--copy-metadata", "mlx-audio",
            "--copy-metadata", "mlx",
            "--copy-metadata", "huggingface-hub",
            str(ROOT / "local_voice" / "mlx_engine.py"),
        ])
    else:
        command.extend([
            "--runtime-hook", str(ROOT / "local_voice" / "frozen_runtime.py"),
            "--collect-all", "chatterbox",
            "--collect-all", "perth",
            "--collect-all", "transformers",
            "--collect-all", "diffusers",
            "--collect-all", "librosa",
            "--collect-all", "pyloudnorm",
            "--collect-all", "safetensors",
            "--copy-metadata", "chatterbox-tts",
            "--copy-metadata", "resemble-perth",
            "--copy-metadata", "requests",
            str(ROOT / "local_voice" / "engine.py"),
        ])
    subprocess.run(command, cwd=ROOT, check=True)
    result = distribution / "jarvis-voice-engine"
    executable = result / ("jarvis-voice-engine.exe" if os.name == "nt" else "jarvis-voice-engine")
    if not executable.is_file():
        raise RuntimeError("PyInstaller did not create the voice engine")
    return result


def _fix_mlx_metallib_layout(engine: Path) -> None:
    """Keep MLX's shader library beside the relocated native library.

    PyInstaller moves libmlx.dylib to ``_internal`` while package data stays
    below ``_internal/mlx``. MLX uses dladdr() to locate its native library and
    then looks for mlx.metallib in the same directory.
    """
    internal = engine / "_internal"
    native_library = internal / "libmlx.dylib"
    packaged_metallib = internal / "mlx" / "lib" / "mlx.metallib"
    colocated_metallib = internal / "mlx.metallib"
    if native_library.is_file():
        if not packaged_metallib.is_file():
            raise FileNotFoundError("MLX engine is missing mlx/lib/mlx.metallib")
        shutil.copy2(packaged_metallib, colocated_metallib)


def _copy_model(model_dir: Path, target: Path, model_files: tuple[str, ...]) -> None:
    target.mkdir(parents=True, exist_ok=True)
    missing = [name for name in model_files if not (model_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"Model directory is incomplete: {', '.join(missing)}")
    for name in model_files:
        # copy2 follows Hugging Face cache symlinks and creates a portable pack.
        shutil.copy2(model_dir / name, target / name, follow_symlinks=True)


def _native_platform() -> tuple[str, str]:
    platforms = {"Darwin": "darwin", "Windows": "win32", "Linux": "linux"}
    architectures = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x64", "AMD64": "x64"}
    return platforms.get(platform.system(), sys.platform), architectures.get(platform.machine(), platform.machine())


def _write_readme(target: Path, version: str, mode: str) -> None:
    if mode == "neutts-nano":
        description = (
            "NeuTTS Nano Q4 with separate German and English JARVIS v2 "
            "voice profiles and an INT8 ONNX decoder"
        )
        watermark = (
            "The source references and the large profile encoder are not "
            "included in the pack."
        )
    elif mode == "moss-nano":
        description = (
            "MOSS-TTS-Nano through MLX with matched English and German "
            "JARVIS v2 clone profiles"
        )
        watermark = "The source reference is not included in the pack."
    elif mode == "multilingual":
        description = "Chatterbox Multilingual with the tuned German JARVIS profile"
        watermark = "Generated Chatterbox audio contains its built-in Perth watermark."
    else:
        description = "Chatterbox Turbo with the English JARVIS profile"
        watermark = "Generated Chatterbox audio contains its built-in Perth watermark."
    target.write_text(
        "JARVIS v4 Offline Voice Pack\n"
        f"Version {version}\n\n"
        "Install this file from JARVIS v4 → Settings → Voice & Animation.\n"
        f"Speech generation stays on the computer and uses {description}.\n"
        f"{watermark}\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable), help="Python with local_voice requirements installed")
    parser.add_argument("--model-dir", required=True, type=Path, help="Complete voice-model snapshot")
    parser.add_argument("--audio-tokenizer-dir", type=Path, help="MOSS audio-tokenizer snapshot")
    parser.add_argument("--profile", required=True, type=Path, help="Derived voice profile")
    parser.add_argument(
        "--profile-de",
        type=Path,
        help="Optional German profile; stored alongside the English profile",
    )
    parser.add_argument(
        "--profile-metadata",
        type=Path,
        help="Reference transcripts for a NeuTTS bilingual profile",
    )
    parser.add_argument("--output-dir", type=Path, default=ROOT / "release")
    parser.add_argument("--version", default="0.5.0")
    parser.add_argument(
        "--mode",
        choices=("turbo", "multilingual", "moss-nano", "neutts-nano"),
        default="turbo",
    )
    parser.add_argument("--profile-source", default="derived-from-user-supplied-video")
    parser.add_argument("--profile-language", choices=("de", "en"), default="en")
    parser.add_argument("--voice-identity", default="JARVIS reference voice")
    parser.add_argument(
        "--cpu-only",
        action="store_true",
        help="Declare a CPU-only runtime in the pack manifest",
    )
    parser.add_argument("--reuse-engine", action="store_true", help="Reuse an existing PyInstaller build")
    args = parser.parse_args()

    # Preserve a virtual-environment launcher instead of resolving its symlink
    # to the base interpreter, otherwise subprocesses lose the venv packages.
    python = Path(os.path.abspath(args.python.expanduser()))
    model_dir = args.model_dir.resolve()
    audio_tokenizer_dir = args.audio_tokenizer_dir.resolve() if args.audio_tokenizer_dir else None
    profile = args.profile.resolve()
    german_profile = args.profile_de.resolve() if args.profile_de else None
    profile_metadata = args.profile_metadata.resolve() if args.profile_metadata else None
    if not python.is_file() or not profile.is_file():
        parser.error("--python and --profile must exist")
    if german_profile and not german_profile.is_file():
        parser.error("--profile-de must exist")
    if german_profile and args.mode not in {"moss-nano", "neutts-nano"}:
        parser.error("--profile-de is supported only for compact bilingual modes")

    if args.mode == "moss-nano" and (not audio_tokenizer_dir or not audio_tokenizer_dir.is_dir()):
        parser.error("--audio-tokenizer-dir is required for moss-nano")
    if args.mode == "neutts-nano":
        if not german_profile:
            parser.error("--profile-de is required for neutts-nano")
        if not profile_metadata or not profile_metadata.is_file():
            parser.error("--profile-metadata is required for neutts-nano")

    engine_dist = BUILD / f"engine-dist-{args.mode}"
    engine_source = engine_dist / "jarvis-voice-engine"
    if not args.reuse_engine or not engine_source.is_dir():
        engine_source = _build_engine(python, engine_dist, args.mode)
    if args.mode == "neutts-nano":
        pack_label = "Smooth-Bilingual-Voice"
    elif args.mode == "moss-nano":
        pack_label = "Fast-Cloned-Voice"
        _fix_mlx_metallib_layout(engine_source)
    elif args.mode == "multilingual":
        pack_label = "German-English-Voice"
    else:
        pack_label = "Video-Voice"

    platform_name, arch = _native_platform()
    pack_name = f"JARVIS-v4-{pack_label}-{args.version}-{platform_name}-{arch}"
    staging_parent = BUILD / "staging"
    pack_root = staging_parent / pack_name
    shutil.rmtree(staging_parent, ignore_errors=True)
    pack_root.mkdir(parents=True)
    shutil.copytree(engine_source, pack_root / "bin", dirs_exist_ok=True)
    if args.mode == "neutts-nano":
        _copy_model(model_dir, pack_root / "models", NEUTTS_MODEL_FILES)
        espeak_source = model_dir / "espeak"
        expected_library = (
            any(espeak_source.glob("libespeak-ng*.dylib"))
            if platform_name == "darwin"
            else any(espeak_source.glob("*espeak-ng*.dll"))
            if platform_name == "win32"
            else any(espeak_source.glob("libespeak-ng.so*"))
        )
        if (
            not espeak_source.is_dir()
            or not (espeak_source / "espeak-ng-data").is_dir()
            or not expected_library
        ):
            raise FileNotFoundError("NeuTTS pronunciation runtime is incomplete")
        shutil.copytree(espeak_source, pack_root / "models" / "espeak")
        profile_name = "profile-en.npy"
    elif args.mode == "moss-nano":
        _copy_model(model_dir, pack_root / "models" / "tts", MOSS_TTS_MODEL_FILES)
        assert audio_tokenizer_dir is not None
        _copy_model(audio_tokenizer_dir, pack_root / "models" / "audio-tokenizer", MOSS_AUDIO_TOKENIZER_FILES)
        profile_name = "profile.safetensors"
    else:
        model_files = MULTILINGUAL_MODEL_FILES if args.mode == "multilingual" else TURBO_MODEL_FILES
        _copy_model(model_dir, pack_root / "models", model_files)
        profile_name = "profile.pt"
    shutil.copy2(profile, pack_root / profile_name)
    if args.mode == "moss-nano" and german_profile:
        shutil.copy2(german_profile, pack_root / "profile-de.safetensors")
    if args.mode == "neutts-nano":
        assert german_profile is not None and profile_metadata is not None
        shutil.copy2(german_profile, pack_root / "profile-de.npy")
        shutil.copy2(profile_metadata, pack_root / "profiles.json")
    _write_readme(pack_root / "README.txt", args.version, args.mode)
    shutil.copy2(ROOT / "local_voice" / "THIRD_PARTY_NOTICES.md", pack_root / "THIRD_PARTY_NOTICES.md")
    _copy_licenses(_voice_site_packages(python), pack_root / "licenses")

    executable = pack_root / "bin" / ("jarvis-voice-engine.exe" if os.name == "nt" else "jarvis-voice-engine")
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if platform_name == "darwin":
        subprocess.run(["codesign", "--force", "--deep", "--sign", "-", str(executable)], check=True)
        subprocess.run(["codesign", "--verify", "--deep", "--strict", str(executable)], check=True)

    files: dict[str, str] = {}
    for target in sorted(path for path in pack_root.rglob("*") if path.is_file()):
        files[target.relative_to(pack_root).as_posix()] = _sha256(target)
    if args.mode == "neutts-nano":
        name = "JARVIS v4 Smooth German & English Voice"
        engine = (
            "Neuphonic NeuTTS Nano via CUDA-capable llama.cpp and ONNX Runtime"
            if platform_name == "win32" and not args.cpu_only
            else "Neuphonic NeuTTS Nano via llama.cpp and ONNX Runtime"
        )
        model = "neuphonic/neutts-nano German & English Q4"
        languages = ["de", "en"]
        license_name = "NeuTTS Open License v1.0; third-party runtime licenses included"
        watermark = "Optional PyTorch Perth watermarker is not included in this compact runtime"
    elif args.mode == "moss-nano":
        name = "JARVIS v4 Matched German & English Voice"
        engine = "OpenMOSS MOSS-TTS-Nano 100M via MLX-Audio"
        model = "mlx-community/MOSS-TTS-Nano-100M"
        languages = ["de", "en"]
        license_name = "Apache-2.0 model; MIT runtime"
        watermark = "No voice-engine watermark declared"
    elif args.mode == "multilingual":
        name = "JARVIS v4 German & English Voice"
        engine = "ResembleAI Chatterbox Multilingual"
        model = "ResembleAI/chatterbox"
        languages = ["de", "en"]
        license_name = "MIT"
        watermark = "Perth implicit audio watermark enabled"
    else:
        name = "JARVIS v4 Offline Video Voice"
        engine = "ResembleAI Chatterbox Turbo 0.1.7"
        model = "ResembleAI/chatterbox-turbo"
        languages = ["en"]
        license_name = "MIT"
        watermark = "Perth implicit audio watermark enabled"
    manifest = {
        "format_version": 1,
        "name": name,
        "version": args.version,
        "platform": platform_name,
        "arch": arch,
        "engine": engine,
        "engine_mode": args.mode,
        "model": model,
        "languages": languages,
        "license": license_name,
        "profile_source": args.profile_source,
        "profile_language": args.profile_language,
        "voice_profiles": (
            {"en": "profile-en.npy", "de": "profile-de.npy"}
            if args.mode == "neutts-nano"
            else {"en": "profile.safetensors", "de": "profile-de.safetensors"}
            if args.mode == "moss-nano" and german_profile
            else {args.profile_language: profile_name}
        ),
        "voice_identity": args.voice_identity,
        "mastering": (
            "reference-video-crisp-v1"
            if args.mode == "neutts-nano"
            else "engine-default"
        ),
        "reference_audio_included": False,
        "watermark": watermark,
        "accelerators": ["cuda", "cpu"] if platform_name == "win32" and not args.cpu_only else ["cpu"],
        "created_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    (pack_root / "voice-pack.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    output = args.output_dir / f"{pack_name}.jarvisvoice"
    output.unlink(missing_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for target in sorted(path for path in pack_root.rglob("*") if path.is_file()):
            archive.write(target, f"{pack_name}/{target.relative_to(pack_root).as_posix()}")
    print(json.dumps({"output": str(output), "bytes": output.stat().st_size, "sha256": _sha256(output)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
