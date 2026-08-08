"""Pure safety and latency bounds for the compact V4 voice engine."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from local_voice import mlx_engine


def test_short_phrases_receive_enough_tokens_to_finish() -> None:
    assert mlx_engine._maximum_audio_tokens("Ja.") >= 56
    assert mlx_engine._maximum_audio_tokens("Yes.") >= 56


def test_long_text_cannot_create_unbounded_audio() -> None:
    text = "JARVIS spricht sicher und kontrolliert. " * 500
    assert mlx_engine._maximum_audio_tokens(text) == 375
    assert mlx_engine._maximum_reasonable_duration(text) == 30.0


def test_normal_sentence_uses_a_smaller_generation_budget() -> None:
    short = mlx_engine._maximum_audio_tokens("Guten Abend. Alle Systeme sind bereit.")
    long = mlx_engine._maximum_audio_tokens(
        "Guten Abend. Alle Systeme sind bereit und ich kann Ihnen heute helfen."
    )
    assert 56 <= short < long < 375


def test_candidate_must_finish_before_token_limit() -> None:
    text = "Einen Moment bitte."
    result = SimpleNamespace(
        audio=np.zeros(24_000, dtype=np.float32),
        sample_rate=24_000,
        token_count=mlx_engine._maximum_audio_tokens(text),
    )

    assert mlx_engine._candidate_is_complete(
        result,
        text,
        mlx_engine._maximum_audio_tokens(text),
    ) is False


def test_long_digital_silence_is_shortened() -> None:
    speech = np.full(12_000, 0.2, dtype=np.float32)
    silence = np.zeros(24_000, dtype=np.float32)
    audio = np.concatenate([speech, silence, speech])

    class FakeMx:
        @staticmethod
        def array(value):
            return np.asarray(value)

    normalized = mlx_engine._normalize_silence(audio, 24_000, FakeMx)

    assert 30_000 < normalized.shape[0] < 34_000
