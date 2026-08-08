from pathlib import Path

import pytest

from scripts.build_voice_pack import _fix_mlx_metallib_layout


def test_fix_mlx_metallib_layout_colocates_shader_library(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    internal = engine / "_internal"
    packaged = internal / "mlx" / "lib" / "mlx.metallib"
    packaged.parent.mkdir(parents=True)
    packaged.write_bytes(b"metal-shaders")
    (internal / "libmlx.dylib").write_bytes(b"native-library")

    _fix_mlx_metallib_layout(engine)

    assert (internal / "mlx.metallib").read_bytes() == b"metal-shaders"


def test_fix_mlx_metallib_layout_rejects_incomplete_mlx_engine(tmp_path: Path) -> None:
    engine = tmp_path / "engine"
    internal = engine / "_internal"
    internal.mkdir(parents=True)
    (internal / "libmlx.dylib").write_bytes(b"native-library")

    with pytest.raises(FileNotFoundError, match="mlx/lib/mlx.metallib"):
        _fix_mlx_metallib_layout(engine)


def test_fix_mlx_metallib_layout_ignores_non_mlx_engine(tmp_path: Path) -> None:
    engine = tmp_path / "engine"

    _fix_mlx_metallib_layout(engine)

    assert not (engine / "_internal" / "mlx.metallib").exists()


def test_compact_voice_build_does_not_bundle_onnx_developer_tools() -> None:
    source = (
        Path(__file__).resolve().parents[1] / "scripts" / "build_voice_pack.py"
    ).read_text(encoding="utf-8")

    assert '"--collect-binaries", "onnxruntime"' in source
    assert '"--collect-all", "onnxruntime"' not in source


def test_windows_voice_workflow_builds_intel_cpu_pack_and_publishes_it() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "build-windows-voice.yml"
    ).read_text(encoding="utf-8")

    assert "runs-on: windows-2022" in workflow
    assert "requirements-windows-cpu.txt" in workflow
    assert "onnxruntime-gpu" not in workflow
    assert "/whl/cu" not in workflow
    assert "Copy-Item assets/voice/jarvis-v3-tuned-1-de.npy" in workflow
    assert "279ff6c17daa00db4cffe872a7a8a9c70814782077f0514c51c6851469d1b22a" in workflow
    assert "JARVIS V3 Old Reference and Tuned 1" in workflow
    assert "reference-video-crisp-v1" in workflow
    assert "--cpu-only" in workflow
    assert "jarvis-v4-windows-intel-cpu-voice" in workflow
    assert "TARGET_RELEASE_TAG: v4.1.1" in workflow
    assert "gh release upload $env:TARGET_RELEASE_TAG" in workflow
    assert "*win32-x64.jarvisvoice" in workflow


def test_windows_cpu_voice_requirements_contain_no_gpu_runtime() -> None:
    requirements = (
        Path(__file__).resolve().parents[1]
        / "local_voice"
        / "requirements-windows-cpu.txt"
    ).read_text(encoding="utf-8")

    assert "onnxruntime==1.23.2" in requirements
    assert "llama-cpp-python==0.3.34" in requirements
    assert "llama-cpp-python/whl/cpu" in workflow
    assert "espeakng-loader==0.2.4" in requirements
    assert "cuda" not in requirements.lower()


def test_cross_platform_voice_workflow_builds_and_publishes_native_packs() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "build-cross-platform-voice.yml"
    ).read_text(encoding="utf-8")

    assert "macos-15" in workflow
    assert "macos-15-intel" in workflow
    assert "ubuntu-24.04" in workflow
    assert "espeakng-loader==0.2.4" in workflow
    assert "prepare_cross_platform_voice.py" in workflow
    assert "jarvis-v3-old-reference-en.npy" in workflow
    assert "jarvis-v3-tuned-1-de.npy" in workflow
    assert "stage_bundled_voice_pack.py" in workflow
    assert "VOICE_VERSION: 4.1.1" in workflow
    assert "TARGET_RELEASE_TAG: v4.1.1" in workflow
    assert 'macos_deployment_target: "14.0"' in workflow
    assert 'cmake_args: "-DCMAKE_OSX_DEPLOYMENT_TARGET=14.0"' in workflow
    assert "MACOSX_DEPLOYMENT_TARGET: ${{ matrix.macos_deployment_target }}" in workflow
    assert "verify_macos_native_compatibility.py" in workflow
    assert "--maximum 14.0" in workflow
    assert "gh release upload" in workflow


def test_macos_native_compatibility_parser_supports_both_load_commands() -> None:
    from scripts.verify_macos_native_compatibility import parse_minimum_versions

    output = """
Load command 9
      cmd LC_VERSION_MIN_MACOSX
  cmdsize 16
  version 10.13
      sdk 15.5
Load command 10
      cmd LC_BUILD_VERSION
  cmdsize 32
 platform MACOS
    minos 13.7
      sdk 14.2
"""

    assert parse_minimum_versions(output) == ("13.7", "10.13")


def test_installer_workflow_consumes_only_the_new_voice_helper() -> None:
    workflow = (
        Path(__file__).resolve().parents[1]
        / ".github"
        / "workflows"
        / "build-installers.yml"
    ).read_text(encoding="utf-8")

    assert "VOICE_RELEASE_TAG: v4.1.1" in workflow
    assert "JARVIS-v4-Smooth-Bilingual-Voice-4.1.1-${{ matrix.voice_platform }}" in workflow
