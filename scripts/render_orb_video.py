"""Pre-render the idle orb animation to a seamlessly looping video.

The live Three.js orb costs real CPU and GPU time for every frame it draws,
which is what heats the machine while nobody is using the app.  A pre-rendered
loop plays through the hardware video decoder instead — a dedicated silicon
block that draws the same picture for a fraction of the energy.

The geometry, camera, colour, and sizing below mirror ``frontend/src/orb.ts``
so the recording is the same artwork.  The one deliberate difference is the
motion: instead of integrating random drift (which never repeats), every
particle follows a sum of sine waves whose periods divide the loop length
exactly, so the last frame flows back into the first with no visible seam.

Usage:
    python3.11 scripts/render_orb_video.py [--seconds 12] [--fps 30]
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / "frontend" / "public" / "assets" / "orb-idle.mp4"

# ── Values mirrored from frontend/src/orb.ts ──
PARTICLES = 2000
CAMERA_Z = 80.0
FOV_DEGREES = 45.0
IDLE_RADIUS = 28.0        # targetRadius in the "idle" state
IDLE_BRIGHTNESS = 0.5     # targetBright
IDLE_POINT_SIZE = 0.35    # targetSize
ORB_COLOR = (0x4C, 0xA8, 0xE8)
CLEAR_COLOR = (0x05, 0x05, 0x08)
# Additive WebGL points bloom brighter than a plain gaussian splat, so the
# splats are gained up to match what the live renderer puts on screen.
GLOW_GAIN = 1.9


def particle_field(rng: np.random.Generator) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Place particles exactly as the live orb seeds them, then give each one a
    periodic orbit in place of the live version's random-walk drift."""
    theta = rng.random(PARTICLES) * math.tau
    phi = np.arccos(2 * rng.random(PARTICLES) - 1)
    # sqrt() biases the cloud outward, matching Math.pow(Math.random(), 0.5).
    radius = np.sqrt(rng.random(PARTICLES)) * 25.0

    base = np.empty((PARTICLES, 3), dtype=np.float64)
    base[:, 0] = radius * np.sin(phi) * np.cos(theta)
    base[:, 1] = radius * np.sin(phi) * np.sin(theta)
    base[:, 2] = radius * np.cos(phi)

    # The live orb only nudges particles toward IDLE_RADIUS, so the cloud keeps
    # the seeded distribution — denser toward the rim, but still filled through
    # the middle. Rescaling every particle onto a shell would hollow it out and
    # read as a much larger, flatter blob.
    base *= 1.0 + 0.12 * (radius / 25.0)[:, None]

    # Small integer harmonics keep every orbit periodic over the loop.
    harmonics = rng.integers(1, 3, size=(PARTICLES, 3)).astype(np.float64)
    phases = rng.random((PARTICLES, 3)) * math.tau
    amplitude = (1.6 + rng.random(PARTICLES) * 2.4)[:, None]
    return base, harmonics, phases * 1.0, amplitude


def gaussian_kernel(size: int, sigma: float) -> np.ndarray:
    axis = np.arange(size) - (size - 1) / 2.0
    grid = np.exp(-(axis[:, None] ** 2 + axis[None, :] ** 2) / (2 * sigma * sigma))
    return grid / grid.max()


def render(seconds: float, fps: int, width: int, height: int, crf: int) -> None:
    rng = np.random.default_rng(20260727)
    base, harmonics, phases, amplitude = particle_field(rng)

    total_frames = int(round(seconds * fps))
    focal = 1.0 / math.tan(math.radians(FOV_DEGREES) / 2.0)
    aspect = width / height
    # The splat has to grow with the output, or particles shrink to specks at
    # higher resolutions. Sized against the 900 px reference render.
    kernel_span = max(9, int(round(9 * height / 900)) | 1)
    kernel = gaussian_kernel(kernel_span, 1.9 * kernel_span / 9.0)
    k_half = kernel.shape[0] // 2
    colour = np.array(ORB_COLOR, dtype=np.float64) / 255.0

    command = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24",
        "-s", f"{width}x{height}", "-r", str(fps),
        "-i", "-",
        # Baseline-friendly H.264 so the hardware decoder handles playback.
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", str(crf), "-preset", "slow", "-movflags", "+faststart",
        "-an", str(OUTPUT),
    ]
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    encoder = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    assert encoder.stdin is not None

    for frame_index in range(total_frames):
        # Loop position in turns; every motion below uses whole multiples of it.
        turn = frame_index / total_frames
        angle = turn * math.tau

        offsets = np.sin(harmonics * angle + phases) * amplitude
        points = base + offsets

        # The live camera drifts but keeps looking at the centre, so the cloud
        # stays framed and only the viewing angle shifts. Rotating the cloud by
        # the same small angles reproduces that parallax without sliding the
        # subject out of frame.
        cloud_z = math.sin(angle) * 8.0
        yaw = math.sin(angle) * (5.0 / CAMERA_Z)
        pitch = math.cos(angle) * (3.0 / CAMERA_Z)

        cos_y, sin_y = math.cos(yaw), math.sin(yaw)
        cos_p, sin_p = math.cos(pitch), math.sin(pitch)
        x, y, z = points[:, 0], points[:, 1], points[:, 2]
        rx = x * cos_y + z * sin_y
        rz = -x * sin_y + z * cos_y
        ry = y * cos_p - rz * sin_p
        rz = y * sin_p + rz * cos_p

        view = np.empty_like(points)
        view[:, 0] = rx
        view[:, 1] = ry
        view[:, 2] = rz + cloud_z - CAMERA_Z

        depth = -view[:, 2]
        visible = depth > 1.0
        if not np.any(visible):
            continue

        vis = view[visible]
        vis_depth = depth[visible]
        ndc_x = (vis[:, 0] / vis_depth) * focal / aspect
        ndc_y = (vis[:, 1] / vis_depth) * focal
        px = ((ndc_x + 1.0) * 0.5 * width).astype(np.int32)
        py = ((1.0 - ndc_y) * 0.5 * height).astype(np.int32)

        # Three.js sizeAttenuation: gl_PointSize = size * (height/2) / -z.
        # Nearer particles read as brighter because their sprite covers more
        # pixels at the same additive weight.
        point_scale = IDLE_POINT_SIZE * (900 / 2.0) / vis_depth
        intensity = GLOW_GAIN * IDLE_BRIGHTNESS * np.clip(point_scale / 2.4, 0.35, 2.6)

        inside = (px >= k_half) & (px < width - k_half) & (py >= k_half) & (py < height - k_half)
        px, py, intensity = px[inside], py[inside], intensity[inside]

        accumulator = np.zeros((height, width), dtype=np.float32)
        for dy in range(kernel.shape[0]):
            for dx in range(kernel.shape[1]):
                weight = kernel[dy, dx]
                if weight <= 0.01:
                    continue
                np.add.at(
                    accumulator,
                    (py + dy - k_half, px + dx - k_half),
                    (intensity * weight).astype(np.float32),
                )

        # Additive blending over the orb's clear colour, same as the renderer.
        rgb = np.clip(accumulator[:, :, None] * colour[None, None, :], 0.0, 1.0)
        background = np.array(CLEAR_COLOR, dtype=np.float64) / 255.0
        frame = np.clip(background[None, None, :] + rgb, 0.0, 1.0)
        encoder.stdin.write((frame * 255).astype(np.uint8).tobytes())

        if frame_index % 30 == 0:
            print(f"  frame {frame_index}/{total_frames}", flush=True)

    encoder.stdin.close()
    encoder.wait()
    if encoder.returncode != 0:
        print(encoder.stderr.read().decode("utf-8", "replace")[-2000:], file=sys.stderr)
        raise SystemExit("ffmpeg failed")
    print(f"Wrote {OUTPUT} ({OUTPUT.stat().st_size / 1_000_000:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # Defaults target a Retina panel at a smooth frame rate. Rendering is a
    # one-off cost; playback is handled by the hardware decoder either way.
    parser.add_argument("--seconds", type=float, default=12.0)
    parser.add_argument("--fps", type=int, default=60)
    parser.add_argument("--width", type=int, default=2880)
    parser.add_argument("--height", type=int, default=1800)
    parser.add_argument("--crf", type=int, default=20)
    args = parser.parse_args()
    render(args.seconds, args.fps, args.width, args.height, args.crf)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
