"""Collect original orb frames from the browser and convert them to MP4.

Companion to ``frontend/src/record.ts``. The browser cannot write to disk, so
it POSTs each lossless PNG frame here. This server assembles the one-time
transition plus a seamless settled loop and encodes the H.264 file the app
ships.

Run it, then open http://localhost:5174/record.html with the dev server up.
It exits by itself once the page reports that every clip is done.
"""

from __future__ import annotations

import http.server
import shutil
import subprocess
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "build" / "orb-clips"
OUTPUT = ROOT / "frontend" / "public" / "assets"
PORT = 5175
STATES = ("idle", "listening", "thinking", "speaking")
FPS = 60
TRANSITION_FRAMES = 2 * FPS
OUTPUT_WIDTH = 3840
OUTPUT_HEIGHT = 2400
# The live renderer fills most of its canvas. The product surface uses it as a
# compact centrepiece so it does not compete with the header or composer.
# Scale the captured pixels inside a full-size matching background rather than
# scaling the <video> element, which would expose a visible rectangular edge.
ARTWORK_SCALE = 0.58

_done = threading.Event()


def encode(state: str) -> None:
    """Assemble an intro followed by a seamless ping-pong settled loop."""
    frames = RAW / state
    target = OUTPUT / f"orb-{state}.mp4"
    source = sorted(frames.glob("*.png"))
    count = len(source)
    if count == 0:
        raise RuntimeError(f"no frames captured for {state}")
    loop_start = 0 if state == "idle" else min(TRANSITION_FRAMES, count - 2)
    # The introduction plays once. The settled part then runs forwards and
    # backwards; both joins are neighbouring source frames, so neither can
    # jump even though the live simulation itself is non-periodic.
    order = list(range(count)) + list(range(count - 2, loop_start, -1))
    staging = RAW / f"{state}-encoded"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    for position, source_index in enumerate(order):
        (staging / f"{position:05d}.png").symlink_to(source[source_index].resolve())

    scaled_width = round(OUTPUT_WIDTH * ARTWORK_SCALE / 2) * 2
    scaled_height = round(OUTPUT_HEIGHT * ARTWORK_SCALE / 2) * 2
    video_filter = (
        f"scale={scaled_width}:{scaled_height}:flags=lanczos,"
        f"pad={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=0x050508"
    )
    command = [
        "ffmpeg", "-y",
        "-framerate", str(FPS),
        "-start_number", "0", "-i", str(staging / "%05d.png"),
        "-vf", video_filter,
        "-c:v", "libx264", "-profile:v", "high", "-pix_fmt", "yuv420p",
        "-crf", "17", "-preset", "slow", "-movflags", "+faststart",
        "-an", str(target),
    ]
    result = subprocess.run(command, capture_output=True)
    if result.returncode != 0:
        print(result.stderr.decode("utf-8", "replace")[-1500:], file=sys.stderr)
        raise RuntimeError(f"ffmpeg failed for {state}")
    size = target.stat().st_size / 1_000_000
    print(
        f"  wrote {target.name} from {count} source frames "
        f"(loop starts at {loop_start / FPS:.1f}s, {size:.1f} MB)",
        flush=True,
    )


class Collector(http.server.BaseHTTPRequestHandler):
    def _allow_cross_origin(self) -> None:
        # The recorder page is served from the dev server on another port.
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        # Without this the image upload's Content-Type fails preflight.
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")

    def do_OPTIONS(self) -> None:  # noqa: N802 - required name
        self.send_response(204)
        self._allow_cross_origin()
        self.end_headers()

    def _reply(self, status: int, body: bytes = b"ok") -> None:
        self.send_response(status)
        self._allow_cross_origin()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:  # noqa: N802 - required name
        parts = [p for p in self.path.split("/") if p]

        if parts == ["done"]:
            self._reply(200)
            _done.set()
            return

        # /reset/<state> — discard an interrupted older capture first.
        if len(parts) == 2 and parts[0] == "reset" and parts[1] in STATES:
            folder = RAW / parts[1]
            if folder.exists():
                shutil.rmtree(folder)
            self._reply(200)
            return

        # /frame/<state>/<index> — one captured image.
        if len(parts) == 3 and parts[0] == "frame" and parts[1] in STATES:
            state, index = parts[1], parts[2]
            length = int(self.headers.get("content-length", "0"))
            payload = self.rfile.read(length)
            folder = RAW / state
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{index}.png").write_bytes(payload)
            if index.endswith("00"):
                print(f"  {state}: frame {index}", flush=True)
            self._reply(200)
            return

        # /encode/<state> — turn the captured frames into the shipped video.
        if len(parts) == 2 and parts[0] == "encode" and parts[1] in STATES:
            state = parts[1]
            try:
                encode(state)
            except Exception as exc:
                print(f"  encoding failed: {exc}", file=sys.stderr, flush=True)
                self._reply(500, b"encode failed")
                return
            self._reply(200)
            return

        self._reply(404, b"unknown path")

    def log_message(self, *_args) -> None:
        return  # the prints above are the useful log


def main() -> int:
    if not shutil.which("ffmpeg"):
        print("ffmpeg is required", file=sys.stderr)
        return 2
    OUTPUT.mkdir(parents=True, exist_ok=True)
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Collector)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Collector listening on http://127.0.0.1:{PORT}")
    print("Open http://localhost:5174/record.html to start recording.")
    # Generous ceiling: a full set of clips takes a few minutes to render.
    if not _done.wait(timeout=3600):
        print("timed out waiting for the recorder", file=sys.stderr)
        server.shutdown()
        return 1
    server.shutdown()
    print("All clips collected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
