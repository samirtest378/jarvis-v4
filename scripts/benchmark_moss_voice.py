"""Render reproducible MOSS voice variants without reloading the model."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from local_voice.mlx_engine import (
    _maximum_audio_tokens,
    _maximum_reasonable_duration,
    _trim_audio,
    _wav_bytes,
)


PRESETS: dict[str, dict[str, float | int | bool]] = {
    "current": {
        "do_sample": True,
        "audio_temperature": 0.72,
        "audio_top_p": 0.90,
        "audio_top_k": 25,
        "audio_repetition_penalty": 1.20,
    },
    "official": {
        "do_sample": True,
        "audio_temperature": 0.80,
        "audio_top_p": 0.95,
        "audio_top_k": 25,
        "audio_repetition_penalty": 1.20,
    },
    "calm": {
        "do_sample": True,
        "audio_temperature": 0.60,
        "audio_top_p": 0.90,
        "audio_top_k": 25,
        "audio_repetition_penalty": 1.20,
    },
    "focused": {
        "do_sample": True,
        "audio_temperature": 0.65,
        "audio_top_p": 0.82,
        "audio_top_k": 20,
        "audio_repetition_penalty": 1.20,
    },
    "greedy": {
        "do_sample": False,
        "audio_temperature": 1.0,
        "audio_top_p": 1.0,
        "audio_top_k": 0,
        "audio_repetition_penalty": 1.20,
    },
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--audio-tokenizer-dir", required=True, type=Path)
    parser.add_argument("--profile", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--text",
        required=True,
        action="append",
        help="Text to render; repeat the option to benchmark several phrases",
    )
    parser.add_argument(
        "--mode",
        choices=("voice_clone", "continuation"),
        default="voice_clone",
    )
    parser.add_argument(
        "--reference-text",
        default="",
        help="Transcript paired with the profile in continuation mode",
    )
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument(
        "--fixed-seed",
        action="store_true",
        help="Reuse --seed for every phrase instead of incrementing it",
    )
    parser.add_argument("--runs", type=int, default=1, help="Variants per preset")
    parser.add_argument(
        "--presets",
        nargs="+",
        choices=tuple(PRESETS),
        default=list(PRESETS),
    )
    args = parser.parse_args()

    for target in (args.model_dir, args.audio_tokenizer_dir):
        if not target.is_dir():
            parser.error(f"Model directory does not exist: {target}")
    if not args.profile.is_file():
        parser.error(f"Profile does not exist: {args.profile}")
    texts = [text.strip() for text in args.text if text.strip()]
    if not texts:
        parser.error("--text cannot be empty")
    if args.runs < 1 or args.runs > 20:
        parser.error("--runs must be between 1 and 20")
    if args.mode == "continuation" and not args.reference_text.strip():
        parser.error("--reference-text is required in continuation mode")

    import mlx.core as mx
    from mlx_audio.tts import load

    args.output_dir.mkdir(parents=True, exist_ok=True)
    load_started = time.monotonic()
    model = load(str(args.model_dir.resolve()))
    profile_data = mx.load(str(args.profile.resolve()))
    prompt_audio_codes = profile_data["prompt_audio_codes"]
    mx.eval(prompt_audio_codes)
    load_seconds = time.monotonic() - load_started

    results = []
    variant_index = 0
    for text_index, text_value in enumerate(texts):
        for preset_name in args.presets:
            settings = PRESETS[preset_name]
            for _run in range(args.runs):
                seed = args.seed if args.fixed_seed else args.seed + variant_index
                variant_index += 1
                mx.random.seed(seed)
                started = time.monotonic()
                token_budget = _maximum_audio_tokens(text_value)
                generated = next(
                    model.generate(
                        text=text_value,
                        prompt_audio_codes=prompt_audio_codes,
                        mode=args.mode,
                        ref_text=(
                            f"{args.reference_text.strip()} "
                            if args.mode == "continuation"
                            else None
                        ),
                        max_tokens=token_budget,
                        text_temperature=1.0,
                        text_top_p=1.0,
                        text_top_k=50,
                        audio_tokenizer_device="cpu",
                        audio_tokenizer_source=str(args.audio_tokenizer_dir.resolve()),
                        **settings,
                    )
                )
                original_duration = (
                    float(generated.audio.shape[0]) / float(generated.sample_rate)
                )
                audio = _trim_audio(
                    generated.audio,
                    text_value,
                    int(generated.sample_rate),
                    mx,
                )
                mx.eval(audio)
                target = args.output_dir / (
                    f"text-{text_index + 1}-{preset_name}-seed-{seed}.wav"
                )
                target.write_bytes(_wav_bytes(audio, int(generated.sample_rate)))
                results.append(
                    {
                        "text": text_value,
                        "preset": preset_name,
                        "seed": seed,
                        "path": str(target.resolve()),
                        "generation_seconds": round(time.monotonic() - started, 3),
                        "duration_seconds": round(
                            float(audio.shape[0]) / float(generated.sample_rate),
                            3,
                        ),
                        "original_duration_seconds": round(original_duration, 3),
                        "token_count": int(generated.token_count),
                        "token_budget": token_budget,
                        "hit_token_budget": int(generated.token_count) >= token_budget,
                        "ended_naturally": (
                            int(generated.token_count) < token_budget
                            and original_duration
                            < (_maximum_reasonable_duration(text_value) - 0.05)
                        ),
                        "settings": settings,
                    }
                )

    print(
        json.dumps(
            {
                "profile": str(args.profile.resolve()),
                "texts": texts,
                "mode": args.mode,
                "reference_text": args.reference_text.strip(),
                "model_load_seconds": round(load_seconds, 3),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
