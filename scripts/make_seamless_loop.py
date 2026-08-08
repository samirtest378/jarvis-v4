"""Turn a captured clip into one that loops without a visible restart.

The live animation drifts randomly, so its last frame never lines up with its
first — played on repeat, the jump back is obvious. This blends the tail of the
capture into its head so the seam disappears.

How it works: with N captured frames and a blend length of K, the output is
M = N - K frames. Output frames K..M-1 are the untouched middle of the capture.
Output frames 0..K-1 fade from source frame M+i to source frame i. The wrap
point (output M-1 → output 0) therefore lands on source frames M-1 → M, which
were consecutive in the original — a real transition, not a cut.

Usage:
    python3.11 scripts/make_seamless_loop.py idle [--blend 60]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
FRAMES = ROOT / "build" / "orb-clips"
OUTPUT = ROOT / "frontend" / "public" / "assets"


def build_pingpong(state: str, fps: int, crf: int) -> None:
    """Play the capture forwards then backwards, which cannot show a seam.

    Cross-fading a loop leaves both ends visible at once for its whole length —
    two particle fields drifting in different directions, which reads as a
    stutter rather than a join. A mirrored clip has no blend at all: the last
    forward frame is followed by its own predecessor, and the final frame of the
    reversed half is followed by the very first frame again. Every step is a
    real neighbouring pair, so the motion never jumps.

    The direction does reverse at the turning points, but a slowly drifting
    cloud has no directional cue for the eye to catch it on.
    """
    source = sorted((FRAMES / state).glob("*.jpg"))
    if len(source) < 3:
        raise SystemExit(f"not enough captured frames in {FRAMES / state}")

    staging = FRAMES / f"{state}-pingpong"
    if staging.exists():
        for old in staging.glob("*.jpg"):
            old.unlink()
    staging.mkdir(parents=True, exist_ok=True)

    # Forward 0..N-1, then back down N-2..1. Both ends stay unduplicated.
    order = list(range(len(source))) + list(range(len(source) - 2, 0, -1))
    for position, index in enumerate(order):
        link = staging / f"{position:05d}.jpg"
        link.symlink_to(source[index].resolve())

    print(f"{state}: {len(source)} frames → {len(order)} mirrored "
          f"({len(order) / fps:.1f}s)", flush=True)

    target = OUTPUT / f"orb-{state}.mp4"
    command = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-pattern_type", "glob", "-i", str(staging / "*.jpg"),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", str(crf), "-preset", "slow", "-movflags", "+faststart",
        "-an", str(target),
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", "replace")[-1500:], file=sys.stderr)
        raise SystemExit("ffmpeg failed")
    print(f"wrote {target.name} ({target.stat().st_size / 1_000_000:.1f} MB)")


def build(state: str, blend: int, fps: int, crf: int) -> None:
    source = sorted((FRAMES / state).glob("*.jpg"))
    if not source:
        raise SystemExit(f"no captured frames in {FRAMES / state}")
    total = len(source)
    if blend >= total // 2:
        raise SystemExit(f"blend of {blend} is too long for {total} frames")

    length = total - blend
    staging = FRAMES / f"{state}-loop"
    if staging.exists():
        for old in staging.glob("*.jpg"):
            old.unlink()
    staging.mkdir(parents=True, exist_ok=True)

    print(f"{state}: {total} frames → {length} with a {blend}-frame blend", flush=True)

    for i in range(length):
        if i >= blend:
            # Untouched middle of the capture.
            Image.open(source[i]).save(staging / f"{i:05d}.jpg", quality=96)
            continue
        # Fade the captured tail into the captured head.
        weight = i / blend
        tail = np.asarray(Image.open(source[length + i]), dtype=np.float32)
        head = np.asarray(Image.open(source[i]), dtype=np.float32)
        merged = tail * (1.0 - weight) + head * weight
        Image.fromarray(np.clip(merged, 0, 255).astype(np.uint8)).save(
            staging / f"{i:05d}.jpg", quality=96
        )
        if i % 20 == 0:
            print(f"  blending {i}/{blend}", flush=True)

    target = OUTPUT / f"orb-{state}.mp4"
    command = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-pattern_type", "glob", "-i", str(staging / "*.jpg"),
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", str(crf), "-preset", "slow", "-movflags", "+faststart",
        "-an", str(target),
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", "replace")[-1500:], file=sys.stderr)
        raise SystemExit("ffmpeg failed")
    print(f"wrote {target.name} ({target.stat().st_size / 1_000_000:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("state", default="idle", nargs="?")
    parser.add_argument("--mode", choices=("pingpong", "crossfade"), default="pingpong")
    parser.add_argument("--blend", type=int, default=60, help="crossfade only: frames to blend")
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--crf", type=int, default=25)
    args = parser.parse_args()
    if args.mode == "pingpong":
        build_pingpong(args.state, args.fps, args.crf)
    else:
        build(args.state, args.blend, args.fps, args.crf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
