"""Score generated speech against a reference with Chatterbox's speaker encoder."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--encoder-weights", required=True, type=Path)
    parser.add_argument("--reference", required=True, type=Path)
    parser.add_argument("samples", nargs="+", type=Path)
    args = parser.parse_args()

    for target in (args.encoder_weights, args.reference, *args.samples):
        if not target.is_file():
            parser.error(f"Audio or model file does not exist: {target}")

    import librosa
    import numpy as np
    import torch
    from chatterbox.models.s3tokenizer import S3_SR
    from chatterbox.models.voice_encoder import VoiceEncoder

    encoder = VoiceEncoder()
    if args.encoder_weights.suffix.lower() == ".safetensors":
        from safetensors.torch import load_file

        encoder_state = load_file(str(args.encoder_weights), device="cpu")
    else:
        encoder_state = torch.load(
            args.encoder_weights,
            map_location="cpu",
            weights_only=True,
        )
    encoder.load_state_dict(encoder_state)
    encoder.eval()

    def embedding(target: Path) -> np.ndarray:
        audio, _ = librosa.load(target, sr=S3_SR, mono=True)
        vector = encoder.embeds_from_wavs([audio], sample_rate=S3_SR)[0]
        return np.asarray(vector, dtype=np.float32)

    reference_embedding = embedding(args.reference)
    results = []
    for sample in args.samples:
        sample_embedding = embedding(sample)
        similarity = float(np.dot(reference_embedding, sample_embedding))
        results.append(
            {
                "sample": str(sample.resolve()),
                "cosine_similarity": round(similarity, 6),
            }
        )
    results.sort(key=lambda item: item["cosine_similarity"], reverse=True)
    print(
        json.dumps(
            {
                "reference": str(args.reference.resolve()),
                "encoder": "Chatterbox VoiceEncoder",
                "results": results,
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
