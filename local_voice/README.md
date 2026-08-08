# Optional JARVIS v4 offline voices

The normal installer deliberately excludes neural speech weights. A separate
`.jarvisvoice` pack contains the native engine, model weights, a derived
speaker profile, an integrity manifest, and third-party notices.

V4's preferred pack uses NeuTTS Nano through llama.cpp and ONNX Runtime:

- `engine_mode: neutts-nano`
- `profile-en.npy` for the original English JARVIS delivery
- `profile-de.npy` for the matched German JARVIS delivery
- automatic profile selection from the requested language while the same
  compact process remains warm
- Apple Accelerate-optimized local inference
- compact runtime memory compared with the legacy studio engine

Legacy `moss-nano`, `turbo`, and `multilingual` packs remain compatible.
Chatterbox packs use `profile.pt` and retain Chatterbox's built-in Perth
watermark.

JARVIS v4 installs the pack into its private user-data directory and talks to
the persistent engine only through a local JSON-lines stdin/stdout protocol.
Text and audio are never uploaded by these engines.

For development, point the backend at an unpacked pack:

```bash
export JARVIS_LOCAL_VOICE_PACK=/absolute/path/to/unpacked-pack
export JARVIS_TTS_PROVIDER=local
```

The app warms the persistent compact helper in the background. Compact engines
have stricter effective startup and generation limits so a broken pack cannot
stall a conversation;
legacy packs retain the configurable `JARVIS_LOCAL_VOICE_START_TIMEOUT`
(default 300 seconds) and `JARVIS_LOCAL_VOICE_SYNTH_TIMEOUT` (default 180
seconds). The compact engine is released after a short idle period to keep
memory use low on 8 GB systems. On macOS,
the system-voice fallback is normalized to PCM WAV because Electron/Web Audio
does not reliably decode AIFF.

Use `scripts/build_voice_pack.py --help` to build a distributable pack and
`scripts/synthesize_voice_sample.py --help` to verify it with a real WAV file.
