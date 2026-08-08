from local_voice import engine
from local_voice import mlx_engine


def test_voice_duration_guard_retries_truncated_speech():
    text = "Guten Abend. Alle Systeme sind bereit."

    assert 1.0 < engine._minimum_reasonable_duration(text) < 3.0


def test_voice_duration_guard_bounds_runaway_repetition():
    short = engine._maximum_reasonable_duration("Good evening. All systems are ready.")
    very_long = engine._maximum_reasonable_duration("Antwort " * 1_000)

    assert 4.0 < short < 10.0
    assert very_long == 30.0


def test_german_clone_avoids_english_reference_accent():
    assert engine._multilingual_generation_settings("de")["cfg_weight"] == 0.0
    assert engine._multilingual_generation_settings("en")["cfg_weight"] == 0.5


def test_fast_clone_bounds_generation_work():
    short = mlx_engine._maximum_audio_tokens("Guten Abend.")
    long = mlx_engine._maximum_audio_tokens("Antwort " * 1_000)

    assert 56 <= short < 100
    assert long == 375
    assert mlx_engine._maximum_reasonable_duration("Antwort " * 1_000) == 30.0
