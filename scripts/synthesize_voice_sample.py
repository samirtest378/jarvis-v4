"""Generate and validate a WAV sample with an unpacked JARVIS v4 voice pack."""

from __future__ import annotations

import argparse
import base64
import json
import selectors
import subprocess
import sys
import time
import wave
from pathlib import Path


def _read_json_line(process: subprocess.Popen[str], timeout: float) -> dict[str, object]:
    if process.stdout is None:
        raise RuntimeError("Voice engine stdout is unavailable")
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Voice engine response timed out")
        if not selector.select(remaining):
            continue
        line = process.stdout.readline()
        if not line:
            raise RuntimeError(f"Voice engine exited with code {process.poll()}")
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pack-dir", required=True, type=Path, help="Unpacked voice-pack directory")
    parser.add_argument("--profile", type=Path, help="Optional voice profile override for comparison tests")
    parser.add_argument("--profile-de", type=Path, help="Optional German profile override")
    parser.add_argument("--profile-metadata", type=Path, help="Optional NeuTTS metadata override")
    parser.add_argument("--output", required=True, type=Path, help="Destination WAV file")
    parser.add_argument(
        "--text",
        default="Good evening, sir. JARVIS v4 is online, and all systems are ready.",
        help="Sentence to synthesize",
    )
    parser.add_argument("--language", choices=("de", "en"), default="en")
    parser.add_argument("--device", choices=("auto", "mps", "cuda", "cpu"), default="auto")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()

    pack = args.pack_dir.expanduser().resolve()
    engine_name = "jarvis-voice-engine.exe" if sys.platform == "win32" else "jarvis-voice-engine"
    engine = pack / "bin" / engine_name
    model_dir = pack / "models"
    manifest_path = pack / "voice-pack.json"
    if not manifest_path.is_file():
        parser.error(f"Voice pack is incomplete: {manifest_path}")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        parser.error(f"Voice-pack manifest is invalid: {exc}")
    mode = manifest.get("engine_mode", "turbo")
    default_profile = (
        "profile-en.npy"
        if mode == "neutts-nano"
        else "profile.safetensors"
        if mode == "moss-nano"
        else "profile.pt"
    )
    profile = (
        args.profile.expanduser().resolve()
        if args.profile
        else pack / default_profile
    )
    german_profile = (
        args.profile_de.expanduser().resolve()
        if args.profile_de
        else pack / ("profile-de.npy" if mode == "neutts-nano" else "profile-de.safetensors")
    )
    profile_metadata = (
        args.profile_metadata.expanduser().resolve()
        if args.profile_metadata
        else pack / "profiles.json"
    )
    missing = [str(path) for path in (engine, model_dir, profile) if not path.exists()]
    if missing:
        parser.error(f"Voice pack is incomplete: {', '.join(missing)}")
    languages = manifest.get("languages", ["en"])
    if mode not in {"turbo", "multilingual", "moss-nano", "neutts-nano"}:
        parser.error("Voice-pack engine mode is invalid")
    if args.language not in languages:
        parser.error(f"Voice pack does not support {args.language!r}")
    if not args.text.strip() or len(args.text) > 4_000:
        parser.error("--text must contain 1 to 4,000 characters")

    started = time.monotonic()
    command = [
            str(engine),
            "--model-dir",
            str(model_dir),
            "--profile",
            str(profile),
            "--device",
            args.device,
            "--mode",
            mode,
        ]
    if mode == "moss-nano" and german_profile.is_file():
        command.extend(["--profile-de", str(german_profile)])
    if mode == "neutts-nano":
        command.extend(
            [
                "--profile-de",
                str(german_profile),
                "--profile-metadata",
                str(profile_metadata),
                "--warm-language",
                args.language,
            ]
        )
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    try:
        ready = _read_json_line(process, args.timeout)
        if ready.get("type") != "ready":
            raise RuntimeError(f"Voice engine did not become ready: {ready.get('error', ready)}")
        ready_seconds = time.monotonic() - started
        if process.stdin is None:
            raise RuntimeError("Voice engine stdin is unavailable")
        request = {
            "type": "synthesize",
            "id": "sample",
            "text": args.text.strip(),
            "language": args.language,
        }
        process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        process.stdin.flush()
        response = _read_json_line(process, args.timeout)
        if response.get("type") != "audio" or not isinstance(response.get("audio"), str):
            raise RuntimeError(f"Voice synthesis failed: {response.get('error', response)}")
        audio = base64.b64decode(response["audio"], validate=True)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_bytes(audio)
        with wave.open(str(args.output), "rb") as wav:
            duration = wav.getnframes() / wav.getframerate()
            details = {
                "output": str(args.output.resolve()),
                "text": args.text.strip(),
                "language": args.language,
                "engine_mode": mode,
                "device": ready.get("device"),
                "sample_rate": wav.getframerate(),
                "channels": wav.getnchannels(),
                "sample_width_bits": wav.getsampwidth() * 8,
                "duration_seconds": round(duration, 3),
                "bytes": len(audio),
                "ready_seconds": round(ready_seconds, 3),
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        print(json.dumps(details, indent=2, ensure_ascii=False))
        return 0
    finally:
        if process.poll() is None:
            try:
                if process.stdin is not None:
                    process.stdin.write('{"type":"shutdown","id":"shutdown"}\n')
                    process.stdin.flush()
                process.wait(timeout=5)
            except (BrokenPipeError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    raise SystemExit(main())
