"""Compact bilingual JARVIS voice engine based on NeuTTS Nano.

This is a deliberately small runtime adaptation of Neuphonic's NeuTTS
``neutts.py`` GGUF/ONNX inference path (NeuTTS 1.4.1). It removes the training
and reference-encoding stack, lazily caches both language backbones, and keeps
the private JSON-lines protocol used by JARVIS.

Modified for JARVIS v4:
- pre-encoded, language-matched JARVIS v2 references;
- lazy German/English backbone caching for fast bilingual conversations;
- bounded sentence chunking and deterministic retry;
- German pronunciation correction for the assistant name;
- no PyTorch dependency in the runtime;
- reference-video matched voice mastering for clear, consistent playback.

NeuTTS model files remain covered by the NeuTTS Open License v1.0. Runtime
dependencies retain their own licenses in the generated voice pack.
"""

from __future__ import annotations

import argparse
import base64
import contextlib
import ctypes
import gc
import io
import json
import math
import os
import platform
import re
import subprocess
import sys
import time
import unicodedata
import wave
from pathlib import Path
from typing import Any

import numpy as np


PROTOCOL_VERSION = 1
SAMPLE_RATE = 24_000
MAX_TEXT_LENGTH = 2_000
MAX_SEGMENT_CHARACTERS = 260
# Deterministic candidates scored against the selected V3 recordings. The
# German Tuned 1 and English Old Reference profiles have different deliveries.
LANGUAGE_SEEDS = {
    "de": (49, 61),
    "en": (7, 42),
}
_PROTOCOL_STDOUT = sys.stdout
_QUOTE_MAP = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")
_PUNCTUATION = re.compile(r"""([,;:.!?…—–()\[\]{}"'])""")
_JARVIS_NAME = re.compile(r"\bjarvis\b", re.IGNORECASE)
_SIR_HONORIFIC = re.compile(r"\bsir\b", re.IGNORECASE)


def _emit(payload: dict[str, Any]) -> None:
    _PROTOCOL_STDOUT.write(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    _PROTOCOL_STDOUT.flush()


def _performance_cores() -> int:
    logical_budget = max(1, (os.cpu_count() or 2) // 2)
    if sys.platform == "darwin":
        try:
            return min(
                logical_budget,
                max(
                    1,
                    int(
                        subprocess.check_output(
                            ["sysctl", "-n", "hw.perflevel0.physicalcpu"],
                            text=True,
                        ).strip()
                    ),
                ),
            )
        except (FileNotFoundError, subprocess.CalledProcessError, ValueError):
            pass
    return logical_budget


class _EspeakRuntime:
    """Minimal eSpeak IPA wrapper for the two voices used by JARVIS.

    Keeping the tiny binding here avoids freezing phonemizer's unrelated
    Festival, Segments, RDF and data-science toolchain into the voice pack.
    """

    def __init__(self, runtime_root: Path) -> None:
        self.runtime_root = runtime_root
        library = self._find_library(runtime_root)
        data = runtime_root / "espeak-ng-data"
        if not data.is_dir():
            raise FileNotFoundError("The bundled pronunciation data is incomplete")

        self.library = ctypes.CDLL(str(library))
        self.library.espeak_Initialize.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_int,
        ]
        self.library.espeak_Initialize.restype = ctypes.c_int
        if self.library.espeak_Initialize(
            0x02,
            0,
            str(runtime_root).encode("utf-8"),
            0,
        ) <= 0:
            raise RuntimeError("The bundled pronunciation runtime could not start")
        self.library.espeak_SetVoiceByName.argtypes = [ctypes.c_char_p]
        self.library.espeak_SetVoiceByName.restype = ctypes.c_int
        self.library.espeak_TextToPhonemes.argtypes = [
            ctypes.POINTER(ctypes.c_char_p),
            ctypes.c_int,
            ctypes.c_int,
        ]
        self.library.espeak_TextToPhonemes.restype = ctypes.c_char_p

    @staticmethod
    def _find_library(runtime_root: Path) -> Path:
        """Resolve the pack-local dynamic library on every supported OS."""
        patterns = (
            ("libespeak-ng*.dylib",)
            if platform.system() == "Darwin"
            else ("espeak-ng*.dll",)
            if platform.system() == "Windows"
            else ("libespeak-ng.so*", "libespeak-ng*.so")
        )
        library = next(
            (
                candidate
                for pattern in patterns
                for candidate in sorted(runtime_root.glob(pattern))
                if candidate.is_file()
            ),
            None,
        )
        if not library:
            raise FileNotFoundError("The bundled pronunciation library is missing")
        return library

    def _phonemize_words(self, text: str, language: str) -> str:
        voice = "de" if language == "de" else "en-us"
        if self.library.espeak_SetVoiceByName(voice.encode("ascii")) != 0:
            raise RuntimeError(f"The {language} pronunciation voice is unavailable")
        text_pointer = ctypes.pointer(ctypes.c_char_p(text.encode("utf-8")))
        phoneme_mode = (ord("_") << 8) | 0x02
        output: list[str] = []
        while text_pointer.contents.value is not None:
            result = self.library.espeak_TextToPhonemes(
                text_pointer,
                1,
                phoneme_mode,
            )
            if result:
                output.append(result.decode("utf-8"))
        line = " ".join(output).strip().replace("\n", " ")
        line = re.sub(r"_+", "_", line).replace("_ ", " ")
        return " ".join(word.replace("_", "") for word in line.split())

    def phonemize(self, text: str, language: str) -> str:
        output = ""
        for part in _PUNCTUATION.split(text):
            if not part:
                continue
            if _PUNCTUATION.fullmatch(part):
                output = output.rstrip() + part + " "
                continue
            words = self._phonemize_words(part.strip(), language) if part.strip() else ""
            if words:
                output += words + " "
        return " ".join(output.split())

    def close(self) -> None:
        terminate = getattr(self.library, "espeak_Terminate", None)
        if terminate:
            terminate()


def _configure_espeak(runtime_root: Path) -> _EspeakRuntime:
    """Load the voice pack's private eSpeak build."""
    library_dir = runtime_root / "espeak"
    return _EspeakRuntime(library_dir)


def _normalize_text(text: str, language: str) -> str:
    normalized = unicodedata.normalize("NFKC", text.translate(_QUOTE_MAP))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if language == "de":
        # German eSpeak reads "Jarvis" with a leading /j/. The hidden spelling
        # below produces the intended English-style /dʒɑːrvɪs/ while the UI
        # continues to display the proper name.
        normalized = _JARVIS_NAME.sub("Dschaarwis", normalized)
        # German eSpeak turns "Sir" into /zi:r/. This internal spelling keeps
        # the unvoiced opening and rounded British-style vowel expected from a
        # JARVIS address while the displayed answer still contains "Sir".
        normalized = _SIR_HONORIFIC.sub("ßör", normalized)
    return normalized


def _split_text(text: str) -> list[str]:
    """Keep prompts inside the 2048-token context without choppy word cuts."""
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= MAX_SEGMENT_CHARACTERS:
        return [text]
    sentences = [part.strip() for part in _SENTENCE_BOUNDARY.split(text) if part.strip()]
    segments: list[str] = []
    current = ""
    for sentence in sentences:
        pieces = (
            [sentence]
            if len(sentence) <= MAX_SEGMENT_CHARACTERS
            else [
                sentence[index : index + MAX_SEGMENT_CHARACTERS]
                for index in range(0, len(sentence), MAX_SEGMENT_CHARACTERS)
            ]
        )
        for piece in pieces:
            candidate = f"{current} {piece}".strip()
            if current and len(candidate) > MAX_SEGMENT_CHARACTERS:
                segments.append(current)
                current = piece
            else:
                current = candidate
    if current:
        segments.append(current)
    return segments


def _token_budget(text: str) -> int:
    spoken = sum(character.isalnum() for character in text)
    return min(900, max(80, spoken * 5 + 50))


def _duration_bounds(text: str) -> tuple[float, float]:
    spoken = sum(character.isalnum() for character in text)
    # NeuTTS can occasionally stop cleanly after the first clause. A very low
    # duration floor accepts that clip because it contains no malformed audio,
    # even though half the sentence is missing. The reference-video voice
    # averages about 14 spoken characters per second; 18 leaves comfortable
    # room for quick delivery while reliably forcing the second deterministic
    # seed for an incomplete take.
    return max(0.45, spoken / 18.0), min(22.0, max(2.0, spoken / 4.0))


def _best_duration_candidate(
    candidates: list[np.ndarray],
    minimum: float,
    maximum: float,
) -> np.ndarray:
    """Keep the closest natural-duration take when every seed misses the range."""
    if not candidates:
        raise RuntimeError("Voice generation failed")

    def distance(audio: np.ndarray) -> float:
        seconds = audio.size / SAMPLE_RATE
        if seconds < minimum:
            return minimum - seconds
        if seconds > maximum:
            return seconds - maximum
        return 0.0

    return min(candidates, key=distance)


def _biquad_coefficients(
    kind: str,
    frequency: float,
    q: float = 0.707,
    gain_db: float = 0.0,
) -> tuple[float, float, float, float, float]:
    """Return normalized RBJ biquad coefficients without a SciPy dependency."""
    omega = 2.0 * math.pi * frequency / SAMPLE_RATE
    cosine = math.cos(omega)
    sine = math.sin(omega)
    alpha = sine / (2.0 * q)
    if kind == "highpass":
        b0 = (1.0 + cosine) / 2.0
        b1 = -(1.0 + cosine)
        b2 = (1.0 + cosine) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cosine
        a2 = 1.0 - alpha
    elif kind == "lowpass":
        b0 = (1.0 - cosine) / 2.0
        b1 = 1.0 - cosine
        b2 = (1.0 - cosine) / 2.0
        a0 = 1.0 + alpha
        a1 = -2.0 * cosine
        a2 = 1.0 - alpha
    elif kind == "peak":
        amplitude = 10.0 ** (gain_db / 40.0)
        b0 = 1.0 + alpha * amplitude
        b1 = -2.0 * cosine
        b2 = 1.0 - alpha * amplitude
        a0 = 1.0 + alpha / amplitude
        a1 = -2.0 * cosine
        a2 = 1.0 - alpha / amplitude
    else:  # pragma: no cover - private callers use fixed filter names
        raise ValueError(f"Unsupported biquad type: {kind}")
    return b0 / a0, b1 / a0, b2 / a0, a1 / a0, a2 / a0


def _apply_biquad(
    samples: np.ndarray,
    coefficients: tuple[float, float, float, float, float],
) -> np.ndarray:
    """Apply a stable direct-form-II filter with constant memory."""
    b0, b1, b2, a1, a2 = coefficients
    output = np.empty_like(samples, dtype=np.float32)
    z1 = 0.0
    z2 = 0.0
    for index, value in enumerate(samples):
        filtered = b0 * float(value) + z1
        z1 = b1 * float(value) - a1 * filtered + z2
        z2 = b2 * float(value) - a2 * filtered
        output[index] = filtered
    return output


def _active_rms(samples: np.ndarray) -> float:
    """Measure speech frames while ignoring punctuation pauses."""
    frame_size = int(SAMPLE_RATE * 0.02)
    complete = samples.size - (samples.size % frame_size)
    if complete < frame_size:
        return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
    frames = samples[:complete].reshape(-1, frame_size)
    levels = np.sqrt(np.mean(np.square(frames), axis=1, dtype=np.float64))
    active = levels[levels >= 0.006]
    if active.size == 0:
        return float(np.sqrt(np.mean(np.square(samples), dtype=np.float64)))
    return float(np.sqrt(np.mean(np.square(active), dtype=np.float64)))


def _master_reference_voice(samples: np.ndarray) -> np.ndarray:
    """Match the clean, compact spectral balance of the reference video.

    NeuTTS output varies in level between German and English and may leave a
    little sub-bass drift or decoder fizz. A tiny deterministic mastering chain
    removes those artifacts, adds controlled consonant presence, and aligns
    active speech to one level. It is pure NumPy so macOS, Windows and Linux
    produce the same samples from the same model output.
    """
    if samples.size == 0:
        return samples
    mastered = samples.astype(np.float32, copy=True)
    mastered -= float(np.mean(mastered, dtype=np.float64))
    mastered = _apply_biquad(
        mastered,
        _biquad_coefficients("highpass", 72.0, q=0.707),
    )
    mastered = _apply_biquad(
        mastered,
        _biquad_coefficients("peak", 3_200.0, q=0.9, gain_db=1.4),
    )
    mastered = _apply_biquad(
        mastered,
        _biquad_coefficients("lowpass", 9_000.0, q=0.707),
    )

    level = _active_rms(mastered)
    if level > 1e-6:
        target = 10.0 ** (-19.0 / 20.0)
        mastered *= float(np.clip(target / level, 0.60, 2.80))
    peak = float(np.max(np.abs(mastered))) if mastered.size else 0.0
    # -1 dBFS leaves room for the operating-system mixer and Bluetooth codecs.
    ceiling = 10.0 ** (-1.0 / 20.0)
    if peak > ceiling:
        mastered *= ceiling / peak
    return mastered


def _normalize_audio(audio: np.ndarray) -> np.ndarray:
    samples = np.asarray(audio, dtype=np.float32).reshape(-1)
    if samples.size == 0:
        return samples

    # Remove only pathological digital-silence runs. Ordinary punctuation
    # pauses remain untouched.
    silent = np.abs(samples) < 0.0008
    minimum_run = int(SAMPLE_RATE * 0.72)
    kept_run = int(SAMPLE_RATE * 0.30)
    pieces: list[np.ndarray] = []
    cursor = 0
    index = 0
    while index < silent.size:
        if not silent[index]:
            index += 1
            continue
        end = index + 1
        while end < silent.size and silent[end]:
            end += 1
        if end - index >= minimum_run:
            pieces.append(samples[cursor : index + kept_run // 2])
            cursor = max(index, end - (kept_run - kept_run // 2))
        index = end
    if cursor:
        pieces.append(samples[cursor:])
        samples = np.concatenate(pieces)

    samples = _master_reference_voice(samples)
    fade = min(int(SAMPLE_RATE * 0.018), samples.size // 2)
    if fade > 1:
        samples[:fade] *= np.linspace(0.0, 1.0, fade, dtype=np.float32)
        samples[-fade:] *= np.linspace(1.0, 0.0, fade, dtype=np.float32)
    return samples


def _wav_bytes(audio: np.ndarray) -> bytes:
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).astype("<i2")
    output = io.BytesIO()
    with wave.open(output, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(SAMPLE_RATE)
        handle.writeframes(pcm.tobytes())
    return output.getvalue()


def _select_onnx_providers(
    available: list[str] | tuple[str, ...],
    requested_device: str,
) -> list[str]:
    """Prefer CUDA while always retaining the CPU execution provider."""
    if requested_device not in {"auto", "cuda", "cpu"}:
        raise ValueError(f"Unsupported voice device: {requested_device}")
    providers = set(available)
    selected: list[str] = []
    if requested_device != "cpu" and "CUDAExecutionProvider" in providers:
        selected.append("CUDAExecutionProvider")
    selected.append("CPUExecutionProvider")
    return selected


def _llama_cuda_supported(requested_device: str) -> bool:
    """Whether this Windows llama.cpp build can offload the TTS backbone."""
    if requested_device == "cpu" or sys.platform != "win32":
        return False
    try:
        from llama_cpp import llama_cpp

        probe = getattr(llama_cpp, "llama_supports_gpu_offload", None)
        return bool(probe and probe())
    except Exception:
        return False


class _Decoder:
    def __init__(self, model_path: Path, requested_device: str) -> None:
        import onnxruntime

        options = onnxruntime.SessionOptions()
        options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_ALL
        options.intra_op_num_threads = _performance_cores()
        options.inter_op_num_threads = 1
        selected = _select_onnx_providers(
            onnxruntime.get_available_providers(),
            requested_device,
        )
        try:
            self.session = onnxruntime.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=selected,
            )
        except Exception:
            # A CUDA build must still speak on PCs without a compatible
            # NVIDIA driver, so retry with the CPU provider.
            self.session = onnxruntime.InferenceSession(
                str(model_path),
                sess_options=options,
                providers=["CPUExecutionProvider"],
            )
        active = self.session.get_providers()
        self.device = "cuda" if active and active[0] == "CUDAExecutionProvider" else "cpu"

    def decode(self, output: str) -> np.ndarray:
        speech_ids = [int(value) for value in re.findall(r"<\|speech_(\d+)\|>", output)]
        if not speech_ids:
            raise ValueError("The voice model returned no speech")
        codes = np.asarray(speech_ids, dtype=np.int32)[None, None, :]
        return self.session.run(None, {"codes": codes})[0][0, 0].astype(np.float32)


class _BilingualVoice:
    def __init__(
        self,
        model_root: Path,
        profile_en: Path,
        profile_de: Path,
        profile_metadata: Path,
        warm_language: str,
        requested_device: str,
    ) -> None:
        started = time.monotonic()
        self.espeak = _configure_espeak(model_root)
        self.models = {
            "de": model_root / "neutts-nano-german-Q4_0.gguf",
            "en": model_root / "neutts-nano-Q4_0.gguf",
        }
        for model in self.models.values():
            if not model.is_file():
                raise FileNotFoundError(f"Voice model is missing: {model.name}")
        self.requested_device = requested_device
        self.decoder = _Decoder(model_root / "neucodec-int8.onnx", requested_device)
        metadata = json.loads(profile_metadata.read_text(encoding="utf-8"))
        self.profiles = {
            "en": np.load(profile_en, allow_pickle=False).astype(np.int32).reshape(-1),
            "de": np.load(profile_de, allow_pickle=False).astype(np.int32).reshape(-1),
        }
        self.reference_text = {
            language: str(metadata[language]["reference_text"]).strip()
            for language in ("de", "en")
        }
        self.reference_phones = {
            language: self.espeak.phonemize(self.reference_text[language], language)
            for language in ("de", "en")
        }
        self.backbones: dict[str, Any] = {}
        self.backbone_devices: dict[str, str] = {}
        # Import and build the first llama.cpp context before announcing that
        # the engine is ready. The backend starts this work in the background
        # while JARVIS is opening or thinking, so the first spoken answer does
        # not absorb a long one-time frozen-runtime cost.
        self._load_backbone(warm_language)
        self.load_seconds = time.monotonic() - started

    def _load_backbone(self, language: str) -> Any:
        cached = self.backbones.get(language)
        if cached is not None:
            return cached
        from llama_cpp import Llama

        use_cuda = _llama_cuda_supported(self.requested_device)

        def create_backbone(cuda: bool) -> Any:
            return Llama(
                model_path=str(self.models[language]),
                verbose=False,
                n_gpu_layers=-1 if cuda else 0,
                n_ctx=2048,
                n_batch=512,
                n_ubatch=512,
                n_threads=_performance_cores(),
                # Batch tokenization used every logical CPU on Windows and
                # could briefly freeze Electron and microphone capture. Match
                # the bounded inference pool so the app stays interactive.
                n_threads_batch=_performance_cores(),
                use_mlock=sys.platform != "win32",
                flash_attn=cuda,
                offload_kqv=cuda,
                seed=LANGUAGE_SEEDS[language][0],
            )

        try:
            backbone = create_backbone(use_cuda)
            device = "cuda" if use_cuda else "cpu"
        except Exception:
            if not use_cuda:
                raise
            # CUDA support may be compiled in even when this PC has no usable
            # driver. The exact same model and profiles can run on its CPU.
            backbone = create_backbone(False)
            device = "cpu"
        self.backbones[language] = backbone
        self.backbone_devices[language] = device
        return backbone

    def warm(self, language: str) -> None:
        """Prepare a language while the cloud model is producing its reply."""
        self._load_backbone(language)

    @property
    def device(self) -> str:
        backbone_cuda = "cuda" in self.backbone_devices.values()
        if backbone_cuda and self.decoder.device == "cuda":
            return "cuda"
        if backbone_cuda:
            return "cuda-backbone"
        if self.decoder.device == "cuda":
            return "cuda-decoder"
        return "apple-accelerate" if sys.platform == "darwin" else "cpu"

    def _prompt(self, text: str, language: str) -> str:
        input_phones = self.espeak.phonemize(text, language)
        codes = "".join(
            f"<|speech_{int(code)}|>" for code in self.profiles[language]
        )
        return (
            "user: Convert the text to speech:"
            f"<|TEXT_PROMPT_START|>{self.reference_phones[language]} {input_phones}"
            f"<|TEXT_PROMPT_END|>\nassistant:<|SPEECH_GENERATION_START|>{codes}"
        )

    def _infer_segment(self, text: str, language: str) -> np.ndarray:
        backbone = self._load_backbone(language)
        prompt = self._prompt(text, language)
        minimum, maximum = _duration_bounds(text)
        candidates: list[np.ndarray] = []
        for seed in LANGUAGE_SEEDS[language]:
            backbone.reset()
            output = backbone(
                prompt,
                max_tokens=_token_budget(text),
                temperature=0.70,
                top_k=40,
                stop=["<|SPEECH_GENERATION_END|>"],
                seed=seed,
            )
            audio = self.decoder.decode(str(output["choices"][0]["text"]))
            candidates.append(audio)
            seconds = audio.size / SAMPLE_RATE
            if minimum <= seconds <= maximum:
                return _normalize_audio(audio)
        best_audio = _best_duration_candidate(candidates, minimum, maximum)
        maximum_frames = int(maximum * SAMPLE_RATE)
        return _normalize_audio(best_audio[:maximum_frames])

    def synthesize(self, text: str, language: str) -> tuple[np.ndarray, float]:
        started = time.monotonic()
        normalized = _normalize_text(text, language)
        segments = _split_text(normalized)
        audio_segments = [
            self._infer_segment(segment, language) for segment in segments
        ]
        if len(audio_segments) == 1:
            audio = audio_segments[0]
        else:
            pause = np.zeros(int(SAMPLE_RATE * 0.09), dtype=np.float32)
            joined: list[np.ndarray] = []
            for index, segment in enumerate(audio_segments):
                if index:
                    joined.append(pause)
                joined.append(segment)
            audio = np.concatenate(joined)
        return audio, time.monotonic() - started

    def close(self) -> None:
        for backbone in self.backbones.values():
            backbone.close()
        self.backbones.clear()
        self.backbone_devices.clear()
        gc.collect()
        self.espeak.close()


def serve(
    model_root: Path,
    profile_en: Path,
    profile_de: Path,
    profile_metadata: Path,
    warm_language: str,
    requested_device: str,
) -> int:
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    with contextlib.redirect_stdout(sys.stderr):
        voice = _BilingualVoice(
            model_root,
            profile_en,
            profile_de,
            profile_metadata,
            warm_language,
            requested_device,
        )
    _emit(
        {
            "type": "ready",
            "protocol": PROTOCOL_VERSION,
            "device": voice.device,
            "sample_rate": SAMPLE_RATE,
            "mode": "neutts-nano",
            "languages": ["de", "en"],
            "features": ["warm-language-cache"],
            "cached_languages": sorted(voice.backbones),
            "load_seconds": round(voice.load_seconds, 3),
        }
    )

    try:
        for raw_line in sys.stdin:
            request_id: Any = None
            try:
                request = json.loads(raw_line)
                request_id = request.get("id")
                if request.get("type") == "shutdown":
                    _emit({"type": "shutdown", "id": request_id, "ok": True})
                    return 0
                if request.get("type") == "warm":
                    language = str(request.get("language", "en")).strip().lower()
                    if language not in {"de", "en"}:
                        raise ValueError("Only German and English speech are supported")
                    with contextlib.redirect_stdout(sys.stderr):
                        voice.warm(language)
                    _emit(
                        {
                            "type": "warm",
                            "id": request_id,
                            "ok": True,
                            "language": language,
                            "cached_languages": sorted(voice.backbones),
                        }
                    )
                    continue
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
                with contextlib.redirect_stdout(sys.stderr):
                    audio, elapsed = voice.synthesize(text, language)
                _emit(
                    {
                        "type": "audio",
                        "id": request_id,
                        "audio": base64.b64encode(_wav_bytes(audio)).decode("ascii"),
                        "sample_rate": SAMPLE_RATE,
                        "duration": round(audio.size / SAMPLE_RATE, 3),
                        "elapsed": round(elapsed, 3),
                        "language": language,
                    }
                )
            except Exception as exc:
                _emit(
                    {
                        "type": "error",
                        "id": request_id,
                        "error": str(exc)[:500],
                    }
                )
    finally:
        voice.close()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--profile-de", required=True, type=Path)
    parser.add_argument("--profile-metadata", type=Path)
    parser.add_argument("--device", default="auto")
    parser.add_argument("--mode", default="neutts-nano")
    parser.add_argument("--warm-language", choices=("de", "en"), default="de")
    args = parser.parse_args()
    metadata = args.profile_metadata or args.profile.with_name("profiles.json")
    if args.mode != "neutts-nano":
        parser.error("This engine only supports neutts-nano")
    return serve(
        args.model_dir.resolve(),
        args.profile.resolve(),
        args.profile_de.resolve(),
        metadata.resolve(),
        args.warm_language,
        args.device,
    )


if __name__ == "__main__":
    raise SystemExit(main())
