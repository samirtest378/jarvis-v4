"""Derive a compact Chatterbox condition profile from a clean voice sample."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a JARVIS offline voice profile")
    parser.add_argument("reference", type=Path, help="Clean WAV sample longer than five seconds")
    parser.add_argument("output", type=Path, help="Destination .pt profile")
    parser.add_argument("--model-dir", required=True, type=Path, help="Unpacked Chatterbox Turbo model directory")
    parser.add_argument("--device", choices=("auto", "mps", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    try:
        import torch
        from chatterbox.tts_turbo import ChatterboxTurboTTS
    except ImportError as exc:
        print("Install local_voice/requirements.txt first.", file=sys.stderr)
        return 2

    device = args.device
    if device == "auto":
        if sys.platform == "darwin" and torch.backends.mps.is_available():
            device = "mps"
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"
    if not args.reference.is_file() or not args.model_dir.is_dir():
        print("Reference audio or model directory is missing.", file=sys.stderr)
        return 2

    model = ChatterboxTurboTTS.from_local(args.model_dir.resolve(), device=device)
    model.prepare_conditionals(str(args.reference.resolve()))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    model.conds.save(args.output)
    print(f"Created {args.output} ({args.output.stat().st_size} bytes) on {device}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
