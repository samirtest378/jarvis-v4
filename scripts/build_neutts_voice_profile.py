"""Encode a clean reference recording into a compact NeuTTS voice profile.

The resulting ``.npy`` file contains only 50 Hz NeuCodec tokens. It does not
contain the source audio and can be used by JARVIS's existing NeuTTS runtime.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CACHE = ROOT / "build" / "neutts-encoder-cache"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reference", type=Path, help="Clean mono WAV reference")
    parser.add_argument("output", type=Path, help="Destination .npy profile")
    parser.add_argument("--cache-dir", type=Path, default=DEFAULT_CACHE)
    parser.add_argument("--device", choices=("auto", "mps", "cuda", "cpu"), default="auto")
    args = parser.parse_args()

    if not args.reference.is_file():
        parser.error(f"reference audio does not exist: {args.reference}")

    import librosa
    import torch
    from neucodec import NeuCodec

    device = args.device
    if device == "auto":
        if torch.backends.mps.is_available():
            device = "mps"
            os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
        elif torch.cuda.is_available():
            device = "cuda"
        else:
            device = "cpu"

    started = time.monotonic()
    codec = NeuCodec.from_pretrained(
        "neuphonic/neucodec",
        cache_dir=args.cache_dir.resolve(),
        local_files_only=True,
    )
    codec.eval().to(device)

    audio, _ = librosa.load(args.reference.resolve(), sr=16_000, mono=True)
    tensor = torch.from_numpy(audio).float().reshape(1, 1, -1).to(device)
    with torch.inference_mode():
        codes = codec.encode_code(tensor).squeeze(0).squeeze(0)
    profile = codes.detach().cpu().numpy().astype(np.int32, copy=False)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    np.save(args.output, profile, allow_pickle=False)
    print(json.dumps({
        "output": str(args.output.resolve()),
        "device": device,
        "reference_seconds": round(len(audio) / 16_000, 3),
        "codes": int(profile.size),
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "reference_audio_included": False,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
