"""Clone the English JARVIS voice into a German/English voice profile.

The shipped voice pack runs Chatterbox *Turbo*, an English-only model: asked to
read German it produces the right voice saying nothing intelligible (verified by
transcribing its output back — "Ich öffne jetzt den Kalender" returned as "Ich,
Ethner, Jetsden, Kalender"). Chatterbox *Multilingual* speaks German properly
and clones a voice from a reference recording, so the two can be combined.

Use a clean English JARVIS recording as the reference. Chatterbox
Multilingual extracts the speaker identity once and can then speak German or
English with that same timbre.

    python scripts/build_german_voice.py --reference path/to/reference.wav

Writes a profile next to the voice pack and a sample for checking.
"""

from __future__ import annotations

import argparse
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REFERENCE = ROOT / "build" / "german-voice" / "jarvis-reference.wav"
DEFAULT_OUTPUT = ROOT / "build" / "german-voice"

GERMAN_CHECKS = [
    "Guten Abend. Alle Systeme sind bereit.",
    "Ich öffne jetzt den Kalender für Sie.",
    "Sie haben heute drei Termine, der erste um neun Uhr.",
]

# Matched to what the shipped English engine uses, so the German voice keeps the
# same delivery rather than the multilingual model's livelier temperature
# default. The model's safer repetition penalty is retained so a rare loop
# cannot turn a short answer into a very long clip.
GERMAN_GENERATION = {
    "temperature": 0.72,
    "top_p": 0.90,
    "repetition_penalty": 2.0,
    # Must stay equal to what `local_voice/engine.py` uses for German, or the
    # samples rendered here are not what the installed app will say.
    #
    # Measured, not assumed. Chatterbox suggests zero CFG across languages to
    # avoid importing an accent. Sweeping the value and scoring the output
    # against the English reference with the speaker encoder gave:
    #   short sentence   0.0 → 0.880   0.3 → 0.885   0.5 → 0.927   0.7 → 0.898
    #   longer sentence  0.0 → 0.924                 0.5 → 0.916
    # The ordering flips between sentences, so the apparent gain at 0.5 is
    # sampler noise, not a better speaker match — and zero is what pronounces
    # German as German. Every candidate transcribed back word for word.
    "cfg_weight": 0.0,
    "exaggeration": 0.45,
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=DEFAULT_REFERENCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--model-dir",
        type=Path,
        default=ROOT / "build" / "mtl-model",
        help="Unpacked Chatterbox Multilingual model directory",
    )
    parser.add_argument("--device", default="auto")
    parser.add_argument(
        "--checks",
        type=int,
        default=len(GERMAN_CHECKS),
        help="Number of German verification clips to render (0 only creates the profile)",
    )
    parser.add_argument(
        "--text",
        action="append",
        dest="check_texts",
        help="Custom German verification/reference sentence; may be repeated",
    )
    args = parser.parse_args()

    if not args.reference.is_file():
        print(f"reference audio not found: {args.reference}", file=sys.stderr)
        return 2

    import torch
    from chatterbox.mtl_tts import ChatterboxMultilingualTTS

    device = args.device
    if device == "auto":
        device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {device}", flush=True)

    # Load from our own copy, never `from_pretrained()`.
    #
    # `from_pretrained()` resolves its checkpoint directory relative to the
    # active voice pack and downloaded the multilingual weights straight over
    # the English ones — which silently broke the shipped voice until the pack
    # was restored from a backup. Keeping the multilingual model in its own
    # directory makes that impossible.
    model_dir = args.model_dir.expanduser().resolve()
    if not (model_dir / "t3_mtl23ls_v2.safetensors").is_file():
        print(
            f"multilingual model not found in {model_dir}.\n"
            "Download it there first — do not point this at the voice pack.",
            file=sys.stderr,
        )
        return 2

    print(f"loading the multilingual model from {model_dir}…", flush=True)
    started = time.monotonic()
    model = ChatterboxMultilingualTTS.from_local(model_dir, device=device)
    print(f"  loaded in {time.monotonic() - started:.0f}s", flush=True)

    print(f"cloning the voice from {args.reference.name}…", flush=True)
    model.prepare_conditionals(str(args.reference))

    args.output.mkdir(parents=True, exist_ok=True)
    profile = args.output / "german-profile.pt"
    model.conds.save(profile)
    print(f"  wrote {profile}", flush=True)

    check_texts = args.check_texts or GERMAN_CHECKS
    for index, sentence in enumerate(check_texts[: max(0, args.checks)]):
        started = time.monotonic()
        with torch.inference_mode():
            audio = model.generate(sentence, language_id="de", **GERMAN_GENERATION)
        target = args.output / f"german-check-{index}.wav"
        samples = audio.detach().cpu().numpy().reshape(-1)
        pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2")
        with wave.open(str(target), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(model.sr)
            handle.writeframes(pcm.tobytes())
        print(f"  [{index}] {time.monotonic() - started:5.1f}s  {target.name}: {sentence}", flush=True)

    print("done — listen to the checks, or transcribe them to verify intelligibility")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
