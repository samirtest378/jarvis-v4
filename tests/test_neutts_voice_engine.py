"""Safety, pronunciation and latency bounds for the NeuTTS voice runtime."""

from __future__ import annotations

import hashlib
import json
import numpy as np
import sys
import types
from pathlib import Path

from local_voice import neutts_engine


def test_german_name_uses_hidden_jarvis_pronunciation() -> None:
    assert (
        neutts_engine._normalize_text(
            "JARVIS ist bereit. Jarvis öffnet den Kalender.",
            "de",
        )
        == "Dschaarwis ist bereit. Dschaarwis öffnet den Kalender."
    )


def test_english_name_is_not_rewritten() -> None:
    assert (
        neutts_engine._normalize_text("JARVIS is ready.", "en")
        == "JARVIS is ready."
    )


def test_german_sir_uses_the_jarvis_style_pronunciation() -> None:
    assert (
        neutts_engine._normalize_text("Guten Abend, Sir. JARVIS ist bereit.", "de")
        == "Guten Abend, ßör. Dschaarwis ist bereit."
    )


def test_minimal_espeak_wrapper_matches_tuned_reference_phonemes() -> None:
    model_root = Path(__file__).resolve().parents[1] / "build" / "neutts-runtime-models"
    if not model_root.is_dir():
        return
    runtime = neutts_engine._configure_espeak(model_root)
    try:
        assert (
            runtime.phonemize("Guten Abend. Dschaarwis ist bereit.", "de")
            == "ɡˈuːtən ˈɑːbənt. dʒˈɑːɾvɪs ɪst bərˈaɪt."
        )
        assert (
            runtime.phonemize("Good evening, sir. All systems are ready.", "en")
            == "ɡˈʊd ˈiːvnɪŋ, sˌɜː. ˈɔːl sˈɪstəmz ɑːɹ ɹˈɛdi."
        )
    finally:
        runtime.close()


def test_long_answers_are_split_at_sentence_boundaries() -> None:
    text = "Alle Systeme sind bereit. " * 30
    segments = neutts_engine._split_text(text)

    assert len(segments) > 1
    assert all(len(segment) <= neutts_engine.MAX_SEGMENT_CHARACTERS for segment in segments)
    assert " ".join(segments).replace("  ", " ").strip() == text.strip()


def test_generation_budget_is_bounded() -> None:
    assert neutts_engine._token_budget("Ja.") >= 80
    assert neutts_engine._token_budget("Sehr langer Satz. " * 500) == 900


def test_incomplete_first_clause_is_below_the_duration_floor() -> None:
    text = "Good evening, sir. Your calendar is ready."
    minimum, maximum = neutts_engine._duration_bounds(text)

    assert minimum > 1.42
    assert maximum > minimum


def test_failed_duration_seeds_keep_the_take_closest_to_natural_speech() -> None:
    too_short = np.zeros(int(neutts_engine.SAMPLE_RATE * 0.8), dtype=np.float32)
    nearly_natural = np.zeros(int(neutts_engine.SAMPLE_RATE * 1.4), dtype=np.float32)
    too_long = np.zeros(int(neutts_engine.SAMPLE_RATE * 4.0), dtype=np.float32)

    selected = neutts_engine._best_duration_candidate(
        [too_short, too_long, nearly_natural],
        minimum=1.5,
        maximum=3.0,
    )

    assert selected is nearly_natural


def test_pathological_silence_is_shortened() -> None:
    speech = np.full(12_000, 0.2, dtype=np.float32)
    silence = np.zeros(24_000, dtype=np.float32)
    normalized = neutts_engine._normalize_audio(
        np.concatenate([speech, silence, speech])
    )

    assert 30_000 < normalized.size < 33_000


def test_reference_voice_mastering_is_clear_levelled_and_headroom_safe() -> None:
    timeline = np.arange(neutts_engine.SAMPLE_RATE, dtype=np.float32) / neutts_engine.SAMPLE_RATE
    speech = (
        0.06 * np.sin(2 * np.pi * 180 * timeline)
        + 0.018 * np.sin(2 * np.pi * 3_200 * timeline)
        + 0.01
    ).astype(np.float32)

    mastered = neutts_engine._master_reference_voice(speech)
    active_db = 20 * np.log10(neutts_engine._active_rms(mastered))

    assert np.isfinite(mastered).all()
    assert abs(float(np.mean(mastered))) < 0.001
    assert -20.0 < active_db < -18.0
    assert float(np.max(np.abs(mastered))) <= (10 ** (-1 / 20)) + 1e-5


def test_windows_voice_prefers_cuda_decoder_with_cpu_fallback() -> None:
    assert neutts_engine._select_onnx_providers(
        ["CPUExecutionProvider", "CUDAExecutionProvider"],
        "auto",
    ) == ["CUDAExecutionProvider", "CPUExecutionProvider"]


def test_cpu_voice_never_selects_cuda() -> None:
    assert neutts_engine._select_onnx_providers(
        ["CUDAExecutionProvider", "CPUExecutionProvider"],
        "cpu",
    ) == ["CPUExecutionProvider"]


def test_voice_rejects_an_unknown_device() -> None:
    import pytest

    with pytest.raises(ValueError, match="Unsupported voice device"):
        neutts_engine._select_onnx_providers(["CPUExecutionProvider"], "quantum")


def test_voice_runtime_keeps_a_bounded_cpu_pool() -> None:
    assert 1 <= neutts_engine._performance_cores() <= max(1, (neutts_engine.os.cpu_count() or 2) // 2)


def test_bilingual_backbones_are_cached_instead_of_reloaded(monkeypatch, tmp_path) -> None:
    created = []

    class FakeBackbone:
        def __init__(self, **settings):
            self.settings = settings
            self.closed = False
            created.append(self)

        def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "llama_cpp", types.SimpleNamespace(Llama=FakeBackbone))
    monkeypatch.setattr(neutts_engine, "_llama_cuda_supported", lambda _device: False)
    monkeypatch.setattr(neutts_engine, "_performance_cores", lambda: 2)

    voice = object.__new__(neutts_engine._BilingualVoice)
    voice.models = {
        "de": tmp_path / "de.gguf",
        "en": tmp_path / "en.gguf",
    }
    voice.requested_device = "auto"
    voice.backbones = {}
    voice.backbone_devices = {}
    voice.espeak = types.SimpleNamespace(close=lambda: None)

    german = voice._load_backbone("de")
    english = voice._load_backbone("en")

    assert voice._load_backbone("de") is german
    assert voice._load_backbone("en") is english
    assert len(created) == 2
    assert not german.closed and not english.closed

    voice.close()
    assert german.closed and english.closed
    assert voice.backbones == {}


def test_macos_performance_cores_stay_inside_the_logical_budget(monkeypatch) -> None:
    monkeypatch.setattr(neutts_engine.sys, "platform", "darwin")
    monkeypatch.setattr(neutts_engine.os, "cpu_count", lambda: 3)
    monkeypatch.setattr(neutts_engine.subprocess, "check_output", lambda *args, **kwargs: "3")

    assert neutts_engine._performance_cores() == 1


def test_production_german_profile_uses_selected_v3_tuned_1_reference() -> None:
    root = Path(__file__).resolve().parents[1]
    profile_path = root / "assets" / "voice" / "jarvis-v3-tuned-1-de.npy"
    metadata = json.loads(
        (root / "assets" / "voice" / "jarvis-v3-selected-profiles.json").read_text(encoding="utf-8")
    )
    profile = np.load(profile_path, allow_pickle=False)

    assert profile.dtype == np.int32
    assert profile.shape == (88,)
    assert metadata["de"]["codes"] == 88
    assert metadata["de"]["reference_seconds"] == 1.76
    assert metadata["de"]["reference_text"] == "Ich öffne jetzt den Kalender für Sie."
    assert hashlib.sha256(profile_path.read_bytes()).hexdigest() == (
        "279ff6c17daa00db4cffe872a7a8a9c70814782077f0514c51c6851469d1b22a"
    )
