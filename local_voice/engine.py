"""Persistent offline voice engine used by the optional JARVIS v4 voice pack.

The process speaks a deliberately small JSON-lines protocol over stdin/stdout.
Keeping the model in one long-lived process avoids reloading several gigabytes
of weights for every sentence.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import io
import json
import multiprocessing
import os
import sys
import wave
from pathlib import Path
from typing import Any


PROTOCOL_VERSION = 1
MAX_TEXT_LENGTH = 4_000
MAX_GENERATION_ATTEMPTS = 2
_PROTOCOL_STDOUT = sys.stdout


def _emit(payload: dict[str, Any]) -> None:
    _PROTOCOL_STDOUT.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
    _PROTOCOL_STDOUT.flush()


def _select_device(requested: str, torch: Any) -> str:
    if requested != "auto":
        return requested
    if sys.platform == "darwin" and torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def _wav_bytes(audio: Any, sample_rate: int) -> bytes:
    """Encode the generated float tensor as browser-friendly 16-bit PCM WAV."""
    import numpy as np

    samples = audio.squeeze().detach().cpu().numpy()
    samples = (np.clip(samples, -1.0, 1.0) * 32767.0).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(samples.tobytes())
    return output.getvalue()


def _minimum_reasonable_duration(text: str) -> float:
    """Detect a rare early-EOS result without adding latency to normal speech."""
    spoken_characters = sum(character.isalnum() for character in text)
    return min(5.0, max(0.65, spoken_characters / 20.0))


def _maximum_reasonable_duration(text: str) -> float:
    """Bound pathological repetitions so playback can never run indefinitely."""
    spoken_characters = sum(character.isalnum() for character in text)
    return min(30.0, max(2.0, spoken_characters / 5.0))


def _trim_pathological_tail(audio: Any, text: str, sample_rate: int, torch: Any) -> Any:
    maximum_samples = int(_maximum_reasonable_duration(text) * sample_rate)
    if audio.numel() <= maximum_samples:
        return audio
    trimmed = audio[..., :maximum_samples].clone()
    fade_samples = min(int(sample_rate * 0.08), maximum_samples)
    if fade_samples > 1:
        fade = torch.linspace(
            1.0,
            0.0,
            fade_samples,
            dtype=trimmed.dtype,
            device=trimmed.device,
        )
        trimmed[..., -fade_samples:] *= fade
    return trimmed


def _multilingual_generation_settings(language: str) -> dict[str, float]:
    """Keep one cloned speaker across both languages.

    The same settings the German profile was built and checked with — see
    `scripts/build_german_voice.py`, which must not drift from this.
    """
    return {
        "temperature": 0.72,
        "top_p": 0.90,
        "repetition_penalty": 2.0,
        # The clone is extracted from an English JARVIS recording, so German
        # is the cross-language case: the model author recommends zero CFG
        # there so no English accent is carried over. Scoring the output
        # against that reference with the speaker encoder shows no reason to
        # disagree — the apparent gain at 0.5 does not survive a second
        # sentence:
        #   short sentence   0.0 → 0.880   0.3 → 0.885   0.5 → 0.927
        #   longer sentence  0.0 → 0.924                 0.5 → 0.916
        # English is not cross-language and keeps the higher weight, which
        # holds it closer to the reference delivery.
        "cfg_weight": 0.0 if language == "de" else 0.5,
        "exaggeration": 0.45,
    }


def _load(
    model_dir: Path,
    profile: Path,
    requested_device: str,
    mode: str,
) -> tuple[Any, Any, str]:
    # Third-party model progress and warnings must never enter protocol stdout.
    with contextlib.redirect_stdout(sys.stderr):
        import torch

        device = _select_device(requested_device, torch)
        if mode == "multilingual":
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS, Conditionals

            model = ChatterboxMultilingualTTS.from_local(model_dir, device=device)
        else:
            from chatterbox.tts_turbo import ChatterboxTurboTTS, Conditionals

            model = ChatterboxTurboTTS.from_local(model_dir, device=device)
        model.conds = Conditionals.load(profile, map_location="cpu").to(device)
    return model, torch, device


def serve(model_dir: Path, profile: Path, requested_device: str, mode: str) -> int:
    if not model_dir.is_dir():
        raise FileNotFoundError(f"Model directory does not exist: {model_dir}")
    if not profile.is_file():
        raise FileNotFoundError(f"Voice profile does not exist: {profile}")

    model, torch, device = _load(model_dir, profile, requested_device, mode)
    _emit({
        "type": "ready",
        "protocol": PROTOCOL_VERSION,
        "device": device,
        "sample_rate": model.sr,
        "mode": mode,
        "languages": ["de", "en"] if mode == "multilingual" else ["en"],
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
            if mode != "multilingual" and language != "en":
                raise ValueError("This voice pack supports English only")

            with torch.inference_mode(), contextlib.redirect_stdout(sys.stderr):
                audio = None
                longest_duration = 0.0
                for _attempt in range(MAX_GENERATION_ATTEMPTS):
                    if mode == "multilingual":
                        candidate = model.generate(
                            text,
                            language_id=language,
                            **_multilingual_generation_settings(language),
                        )
                    else:
                        candidate = model.generate(
                            text,
                            temperature=0.72,
                            top_p=0.90,
                            repetition_penalty=1.25,
                        )
                    duration = float(candidate.numel()) / float(model.sr)
                    if audio is None or duration > longest_duration:
                        audio = candidate
                        longest_duration = duration
                    if duration >= _minimum_reasonable_duration(text):
                        break
                if audio is None:
                    raise RuntimeError("Voice generation returned no audio")
                audio = _trim_pathological_tail(audio, text, model.sr, torch)
            encoded = base64.b64encode(_wav_bytes(audio, model.sr)).decode("ascii")
            _emit({
                "type": "audio",
                "id": request_id,
                "format": "wav",
                "sample_rate": model.sr,
                "audio": encoded,
            })
        except Exception as exc:
            _emit({
                "type": "error",
                "id": request_id,
                "error": f"{type(exc).__name__}: {exc}"[:500],
            })
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="JARVIS v4 offline video-voice engine")
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--device", choices=("auto", "mps", "cuda", "cpu"), default="auto")
    parser.add_argument("--mode", choices=("turbo", "multilingual"), default="turbo")
    return parser.parse_args()


def main() -> int:
    # Required when PyTorch or Perth launches a helper from a frozen executable.
    multiprocessing.freeze_support()
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
    args = parse_args()
    try:
        return serve(args.model_dir.resolve(), args.profile.resolve(), args.device, args.mode)
    except Exception as exc:
        print(f"JARVIS v4 voice engine could not start: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
