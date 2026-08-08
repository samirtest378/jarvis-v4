# JARVIS v4 selected V3 voice assets

The normal macOS and Windows builds use the same compact NeuTTS model family
and the same profile files: the selected V3 old-reference English profile plus
the selected V3 Tuned 1 German profile. This keeps the voice identity consistent when
a conversation switches languages or operating systems.

`jarvis-v2-moss-profile.safetensors` is the compact speaker-conditioning
profile produced from the existing JARVIS v2 reference during the Claude
development session on 2026-07-29.

- Runtime: MOSS-TTS-Nano 100M through MLX-Audio
- Languages: German and English
- Target device: Apple Silicon / Metal
- Reference audio included in releases: no
- Profile content: derived audio-token conditioning codes only
- Development preview: `jarvis-v4-voice-preview-de.wav`

The profiles are intentionally separate from the model weights. Apple-Silicon
packs can be built with `scripts/build_voice_pack.py --mode moss-nano`.

`jarvis-v3-old-reference-en.npy` is the compact English profile derived from the
selected old JARVIS v3 reference.
`jarvis-video-2026-moss-en.safetensors` is an optional Apple-Silicon video profile.
`jarvis-v3-tuned-1-de.npy` is the production German NeuTTS profile derived from
the selected V3 Tuned 1 sample ("Ich öffne jetzt den Kalender für Sie.").
`jarvis-video-2026-moss-de.safetensors` is an experimental German clone.

Generated, mastered output previews are available in `previews/` for both
selected profiles. They are safe demonstrations of the runtime output; the
private source recordings are not included.

The production NeuTTS engine applies the same `reference-video-crisp-v1`
mastering to both languages: sub-bass/DC cleanup, controlled consonant
presence, a 9 kHz artifact guard, matched active-speech level, and -1 dBFS
headroom. It uses pure NumPy so macOS, Windows, and Linux render it identically.

The original recordings are not included; only compact derived conditioning
codes are published. The
experimental MOSS German profile is retained for development comparison only.
It is not selected automatically.

The model and runtime licenses do not grant rights to a speaker identity,
character, brand, or reference recording. Those rights must be cleared before
public distribution.
