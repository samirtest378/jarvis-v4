"""Fast persistent German/English JARVIS voice engine for Apple Silicon.

The engine runs MOSS-TTS-Nano through MLX and exposes the same private
JSON-lines protocol as the legacy Chatterbox helper. A compact set of audio
tokens stores the cloned JARVIS v2 speaker identity; the source recording is
not needed at runtime.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import os
import sys
import time
import types
import wave
import importlib.util
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
MAX_TEXT_LENGTH = 2_000
MAX_GENERATION_ATTEMPTS = 2
_PROTOCOL_STDOUT = sys.stdout


def _emit(payload: dict[str, Any]) -> None:
    _PROTOCOL_STDOUT.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    _PROTOCOL_STDOUT.flush()


def _maximum_reasonable_duration(text: str) -> float:
    spoken_characters = sum(character.isalnum() for character in text)
    return min(30.0, max(2.0, spoken_characters / 5.0))


def _minimum_reasonable_duration(text: str) -> float:
    """Reject rare early-EOS clips without slowing normal answers."""
    spoken_characters = sum(character.isalnum() for character in text)
    return min(5.0, max(0.65, spoken_characters / 20.0))


def _maximum_audio_tokens(text: str) -> int:
    """Bound latency while leaving enough room for natural sentence endings."""
    spoken_characters = sum(character.isalnum() for character in text)
    return min(375, max(56, int(spoken_characters * 1.7) + 24))


def _trim_audio(audio: Any, text: str, sample_rate: int, mx: Any) -> Any:
    maximum_frames = int(_maximum_reasonable_duration(text) * sample_rate)
    if audio.shape[0] <= maximum_frames:
        return audio
    trimmed = audio[:maximum_frames]
    fade_frames = min(int(sample_rate * 0.08), maximum_frames)
    if fade_frames > 1:
        fade = mx.linspace(1.0, 0.0, fade_frames)
        if len(trimmed.shape) == 2:
            fade = fade[:, None]
        trimmed = mx.concatenate(
            [trimmed[:-fade_frames], trimmed[-fade_frames:] * fade],
            axis=0,
        )
    return trimmed


def _normalize_silence(audio: Any, sample_rate: int, mx: Any) -> Any:
    """Shorten model glitches while keeping natural pauses and word endings.

    MOSS Nano occasionally inserts multi-second digital-silence gaps between
    otherwise correct words. Those gaps made the clone sound broken and also
    delayed playback. Only runs of near-zero samples longer than 650 ms are
    reduced; ordinary punctuation pauses are untouched.
    """
    import numpy as np

    samples = np.asarray(audio)
    if samples.size == 0:
        return audio
    levels = np.max(np.abs(samples), axis=1) if samples.ndim == 2 else np.abs(samples)
    silent = levels < 0.001
    minimum_run = max(1, int(sample_rate * 0.65))
    kept_run = max(1, int(sample_rate * 0.28))
    pieces: list[Any] = []
    cursor = 0
    index = 0
    while index < silent.shape[0]:
        if not silent[index]:
            index += 1
            continue
        end = index + 1
        while end < silent.shape[0] and silent[end]:
            end += 1
        if end - index >= minimum_run:
            keep_before = kept_run // 2
            keep_after = kept_run - keep_before
            pieces.append(samples[cursor : min(end, index + keep_before)])
            cursor = max(index, end - keep_after)
        index = end
    if cursor == 0:
        return audio
    pieces.append(samples[cursor:])
    normalized = np.concatenate(pieces, axis=0)
    return mx.array(normalized)


def _wav_bytes(audio: Any, sample_rate: int) -> bytes:
    import numpy as np

    samples = np.asarray(audio)
    if samples.ndim == 1:
        channels = 1
    elif samples.ndim == 2 and samples.shape[1] in {1, 2}:
        channels = int(samples.shape[1])
    else:
        raise ValueError("Voice model returned an unsupported audio shape")
    pcm = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm.tobytes())
    return output.getvalue()


def _load_frozen_source(module_name: str, source: Path) -> Any:
    if not source.is_file():
        raise FileNotFoundError(f"Frozen voice runtime is missing {source.name}")
    spec = importlib.util.spec_from_file_location(module_name, source)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not initialize frozen module {module_name}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _install_frozen_runtime_shims() -> None:
    """Load only the small MLX pieces required by MOSS Nano.

    ``mlx_audio.codec`` eagerly imports all codec families. In a frozen helper
    that drags in unrelated transformer/scipy stacks and adds tens of seconds
    to the first spoken reply. ``mlx_lm`` similarly imports Transformers even
    though Nano only needs its standalone sampling helpers. The build stores
    those two upstream sources as data and these narrowly scoped modules expose
    only what Nano requests. Normal development uses the installed packages.
    """
    if not getattr(sys, "frozen", False):
        return
    runtime = Path(getattr(sys, "_MEIPASS")) / "_jarvis_voice"

    mlx_lm = types.ModuleType("mlx_lm")
    mlx_lm.__path__ = []
    sys.modules["mlx_lm"] = mlx_lm
    sampling = _load_frozen_source(
        "mlx_lm.sample_utils",
        runtime / "sample_utils.py",
    )
    mlx_lm.sample_utils = sampling

    module = _load_frozen_source(
        "_jarvis_moss_audio_tokenizer",
        runtime / "moss_audio_tokenizer.py",
    )
    codec = types.ModuleType("mlx_audio.codec")
    codec.MossAudioTokenizer = module.MossAudioTokenizer
    sys.modules["mlx_audio.codec"] = codec


def _load(
    model_root: Path,
    profile: Path,
    german_profile: Path | None,
) -> tuple[Any, Any, dict[str, Any], Path, float]:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    started = time.monotonic()
    with contextlib.redirect_stdout(sys.stderr):
        import mlx.core as mx
        from mlx_audio.tts import load

        tts_model = model_root / "tts"
        audio_tokenizer = model_root / "audio-tokenizer"
        if not tts_model.is_dir() or not audio_tokenizer.is_dir():
            raise FileNotFoundError("MOSS voice-pack model directories are incomplete")
        _install_frozen_runtime_shims()
        model = load(str(tts_model))
        profiles: dict[str, Any] = {}
        for language, target in (
            ("en", profile),
            ("de", german_profile or profile),
        ):
            profile_data = mx.load(str(target))
            prompt_audio_codes = profile_data.get("prompt_audio_codes")
            if prompt_audio_codes is None:
                raise ValueError(f"{language.upper()} voice profile contains no prompt_audio_codes")
            mx.eval(prompt_audio_codes)
            profiles[language] = prompt_audio_codes
    return model, mx, profiles, audio_tokenizer, time.monotonic() - started


def _candidate_is_complete(result: Any, text: str, token_budget: int) -> bool:
    duration = float(result.audio.shape[0]) / float(result.sample_rate)
    return (
        duration >= _minimum_reasonable_duration(text)
        and int(result.token_count) < token_budget
        and duration < (_maximum_reasonable_duration(text) + 0.05)
    )


def serve(model_root: Path, profile: Path, german_profile: Path | None = None) -> int:
    model, mx, profiles, audio_tokenizer, load_seconds = _load(
        model_root,
        profile,
        german_profile,
    )
    _emit({
        "type": "ready",
        "protocol": PROTOCOL_VERSION,
        "device": "mlx-metal",
        "sample_rate": int(model.sample_rate),
        "mode": "moss-nano",
        "languages": ["de", "en"],
        "load_seconds": round(load_seconds, 3),
    })

    for raw_line in sys.stdin:
        request_id: Any = None
        try:
            request = json.loads(raw_line)
            request_id = request.get("id")
            if request.get("type") == "shutdown":
                _emit({"type": "shutdown", "id": request_id, "ok": True})
                return 0
            if request.get("type") != "synthesize":
                raise ValueError("Unsupported request type")
            text = str(request.get("text", "")).strip()
            if not text:
                raise ValueError("Text is empty")
            if len(text) > MAX_TEXT_LENGTH:
                raise ValueError(f"Text exceeds {MAX_TEXT_LENGTH} characters")
            language = str(request.get("language", "en")).strip().lower()
            if language not in {"de", "en"}:
                raise ValueError("Only German and English speech are supported")

            started = time.monotonic()
            with contextlib.redirect_stdout(sys.stderr):
                token_budget = _maximum_audio_tokens(text)
                result = None
                longest_result = None
                longest_duration = -1.0
                # Resetting MLX makes the voice reproducible across launches.
                # Attempt two is used only for early-EOS or a hit token limit.
                for attempt in range(MAX_GENERATION_ATTEMPTS):
                    mx.random.seed(41 + attempt * 97)
                    candidate = next(model.generate(
                        text=text,
                        prompt_audio_codes=profiles[language],
                        max_tokens=token_budget,
                        temperature=0.72,
                        top_p=0.90,
                        repetition_penalty=1.2,
                        audio_tokenizer_device="cpu",
                        audio_tokenizer_source=str(audio_tokenizer),
                    ))
                    candidate_duration = (
                        float(candidate.audio.shape[0]) / float(candidate.sample_rate)
                    )
                    if candidate_duration > longest_duration:
                        longest_result = candidate
                        longest_duration = candidate_duration
                    if _candidate_is_complete(candidate, text, token_budget):
                        result = candidate
                        break
                result = result or longest_result
                if result is None:
                    raise RuntimeError("Voice generation returned no audio")
                audio = _trim_audio(result.audio, text, int(result.sample_rate), mx)
                audio = _normalize_silence(audio, int(result.sample_rate), mx)
                mx.eval(audio)
            encoded = base64.b64encode(_wav_bytes(audio, int(result.sample_rate))).decode("ascii")
            _emit({
                "type": "audio",
                "id": request_id,
                "audio": encoded,
                "format": "wav",
                "sample_rate": int(result.sample_rate),
                "language": language,
                "generation_seconds": round(time.monotonic() - started, 3),
            })
        except Exception as exc:
            _emit({"type": "error", "id": request_id, "error": str(exc)[:500]})
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument(
        "--profile-de",
        type=Path,
        help="Optional German profile; defaults to a sibling profile-de.safetensors",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument("--mode", default="moss-nano")
    args = parser.parse_args()
    if args.mode != "moss-nano":
        parser.error("This engine only supports moss-nano mode")
    german_profile = args.profile_de
    if german_profile is None:
        sibling = args.profile.with_name("profile-de.safetensors")
        german_profile = sibling if sibling.is_file() else None
    try:
        return serve(
            args.model_dir.resolve(),
            args.profile.resolve(),
            german_profile.resolve() if german_profile else None,
        )
    except Exception as exc:
        _emit({"type": "error", "id": None, "error": str(exc)[:500]})
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
