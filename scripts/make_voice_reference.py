"""Build the cleanest possible reference recording of the English JARVIS voice.

Chatterbox only looks at the opening of a reference: 10 seconds for the decoder,
6 for the speaker encoder. Everything after that is ignored, so a longer file is
not a better one — what matters is that those first seconds are dense, evenly
levelled speech with no silence wasting them.

This asks the shipped English voice to read phonetically varied lines, trims the
silence out of each, normalises them to a common level, and concatenates the
result. Compared with simply gluing raw clips together, that packs noticeably
more actual voice into the window the model reads.
"""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys
import time
import wave
from pathlib import Path

import numpy as np

PACK = Path.home() / "Library/Application Support/JARVIS v4/voice-pack/current"
DEFAULT_OUTPUT = Path.home() / "jarvis-v4" / "build" / "german-voice" / "jarvis-reference.wav"

# Chosen for phonetic spread — a range of vowels, plosives and sibilants — and
# for being the register JARVIS actually speaks in.
SENTENCES = [
    "Good evening, sir. All systems are online and standing by.",
    "I have checked your calendar; there are three appointments today.",
    "The first begins at nine, and the weather will stay clear.",
    "Certainly. I will open that for you right away.",
    "Your message has been noted, and everything is running normally.",
    "Six hundred and forty files were archived without any errors.",
    "Shall I prepare a summary before the meeting starts?",
]

TARGET_SECONDS = 12.0  # a little past the 10s the decoder reads, as headroom


def trim_silence(samples: np.ndarray, threshold: float = 0.015) -> np.ndarray:
    """Drop leading and trailing near-silence, keeping a short natural margin."""
    loud = np.abs(samples) > threshold
    if not loud.any():
        return samples
    first, last = int(np.argmax(loud)), len(loud) - int(np.argmax(loud[::-1]))
    margin = 400  # ~17 ms, so words do not start abruptly
    return samples[max(0, first - margin):min(len(samples), last + margin)]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    engine = PACK / "bin" / "jarvis-voice-engine"
    if not engine.is_file():
        print(f"voice engine not found: {engine}", file=sys.stderr)
        return 2

    process = subprocess.Popen(
        [str(engine), "--model-dir", str(PACK / "models"), "--profile", str(PACK / "profile.pt")],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, bufsize=1,
    )
    assert process.stdin and process.stdout

    ready = json.loads(process.stdout.readline())
    rate = int(ready.get("sample_rate", 24000))
    print(f"engine ready on {ready.get('device')} at {rate} Hz", flush=True)

    collected: list[np.ndarray] = []
    total = 0.0
    for index, sentence in enumerate(SENTENCES):
        if total >= TARGET_SECONDS:
            break
        started = time.monotonic()
        process.stdin.write(json.dumps({"type": "synthesize", "id": index, "text": sentence}) + "\n")
        process.stdin.flush()
        reply = json.loads(process.stdout.readline())
        if reply.get("type") != "audio":
            print(f"  [{index}] failed: {reply.get('error')}", file=sys.stderr, flush=True)
            continue

        raw = base64.b64decode(reply["audio"])
        samples = np.frombuffer(raw[44:], dtype="<i2").astype(np.float32) / 32768.0
        before = len(samples) / rate
        samples = trim_silence(samples)
        peak = float(np.max(np.abs(samples))) or 1.0
        # Even levels matter: the encoder averages across the window, and one
        # quiet clip drags the whole speaker estimate toward that reading.
        samples = samples * (0.92 / peak)
        collected.append(samples)
        total += len(samples) / rate
        print(
            f"  [{index}] {time.monotonic() - started:5.1f}s  "
            f"{before:.1f}s → {len(samples)/rate:.1f}s trimmed  (total {total:.1f}s)",
            flush=True,
        )

    process.stdin.write(json.dumps({"type": "shutdown"}) + "\n")
    process.stdin.flush()
    process.wait(timeout=60)

    if not collected:
        print("no audio captured", file=sys.stderr)
        return 1

    joined = np.concatenate(collected)[: int(TARGET_SECONDS * rate)]
    pcm = (np.clip(joined, -1.0, 1.0) * 32767.0).astype("<i2")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(args.output), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(pcm.tobytes())
    print(f"wrote {args.output} ({len(joined)/rate:.1f}s of dense reference speech)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
