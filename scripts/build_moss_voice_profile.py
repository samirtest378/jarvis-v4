"""Create a compact MOSS-TTS-Nano clone profile from a reference recording."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", required=True, type=Path)
    parser.add_argument("--audio-tokenizer-dir", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--reference-text", default="")
    args = parser.parse_args()
    for path in (args.model_dir, args.audio_tokenizer_dir):
        if not path.is_dir():
            parser.error(f"model directory does not exist: {path}")
    if not args.reference.is_file():
        parser.error(f"reference audio does not exist: {args.reference}")

    import mlx.core as mx
    from mlx_audio.tts import load

    started = time.monotonic()
    model = load(str(args.model_dir.resolve()))
    prompt_audio_codes = model.encode_reference_audio(
        str(args.reference.resolve()),
        device="cpu",
        source=str(args.audio_tokenizer_dir.resolve()),
    )
    mx.eval(prompt_audio_codes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    mx.save_safetensors(
        str(args.output),
        {"prompt_audio_codes": prompt_audio_codes.astype(mx.int32)},
        metadata={
            "format": "jarvis-moss-voice-profile-v1",
            "reference_language": "en",
            "reference_text": args.reference_text.strip(),
        },
    )
    print(json.dumps({
        "output": str(args.output.resolve()),
        "shape": list(prompt_audio_codes.shape),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "reference_audio_included": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
