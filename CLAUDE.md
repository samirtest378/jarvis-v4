# JARVIS v4 — contributor context

JARVIS v4 is a cross-platform Electron desktop assistant with a Python/FastAPI
sidecar, a Vite/TypeScript/Three.js interface, SQLite memory, optional macOS
automation, provider-neutral LLM access, and cloud-first speech.

## Staying cheap on the machine

Measured idle cost: ~5% CPU for the live animation, plus ~5-6% while the wake
phrase is listening. Every number below came from comparing CPU-time deltas
over a fixed window — `ps %CPU` averages since process start and is useless
here. Measure before and after any change to these:

- **`backdrop-filter` over moving content is the most expensive thing in this
  interface.** It re-blurs its region every time the pixels behind it change,
  so over the animated canvas that is one blur pass per element per frame — it
  measured **24.5% of a core in the GPU process alone**, more than the
  animation it was blurring. The chrome that permanently floats over the orb
  (`#connection-status`, `#controls button`, `.quick-action`, `#composer`,
  `.message`) therefore uses flat fills; only on-demand panels keep real blur.
  Removing that is what made the live animation affordable — it had nothing to
  do with the particle simulation.
- **The animation is live and runs at full rate.** No freezing, no frame-rate
  cap: both were visible. Motion is still scaled by elapsed time (`k` and
  `decay()` in `orb.ts`) so it stays correct at any rate — never reintroduce
  per-frame constants without that scaling.
- **Decorative CSS loops pause** via `body.is-resting` (`style.css`), for the
  same blur reason.
- **No idle timers.** The periodic context thread only starts when one of its
  opt-in sources is configured.
- **Simple commands skip the model.** `resolve_direct_command()` answers
  "open YouTube", "öffne Kalender", "show my mail" directly; anything ambiguous
  falls through to the model untouched.
- **Speech recognition is cloud-first** (`JARVIS_STT_PROVIDER=auto`), with the
  bundled whisper.cpp engine as the fallback — it releases its model after 30
  idle minutes when hands-free listening is off. `JARVIS_SPEECH_LANGUAGE=auto` sends no language hint, which is
  what lets German and English be mixed freely.
- **The wake phrase costs ~5-6% CPU** and cannot be optimised away — the load
  is in the recognition itself, not the UI (tried and measured). It is off on
  first run for battery life and microphone privacy, then persists the user's
  explicit choice.

## The cloned voice packs

The normal V4 pack uses compact MOSS-TTS-Nano through MLX. It stores separate
English and German speaker-token profiles, selects them per request, and
releases its process after 45 quiet seconds. The profile files contain tokens,
not the source recordings.

Legacy V3 installations may still contain two Chatterbox packs:

    voice-pack/current       Chatterbox Turbo, English only
    voice-pack/multilingual  Chatterbox Multilingual, German + English

Two things to keep straight when touching this:

- **Never let `from_pretrained()` near a voice pack.** It resolves its
  checkpoint directory relative to the active pack and once downloaded the
  multilingual weights straight over the English ones, silently breaking the
  shipped voice. `scripts/build_german_voice.py` loads from `build/mtl-model`
  with `from_local()` for exactly this reason.
- **The manifest must match the weights on disk.** `engine_mode` selects both
  the required model file list and the engine's `--mode`; a manifest promising
  `multilingual` next to Turbo weights makes `_local_voice_paths()` return
  `None` and the voice disappears with no error. MOSS packs that declare a
  German `voice_profiles` entry must include `profile-de.safetensors`.
  `scripts/repair_english_voice_pack.py` puts `current` back in that case.

## Start and build

Follow `README.md`. The supported development path is:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --require-hashes -r requirements-build.lock.txt
npm run setup
npm run dev
```

Do not generate local TLS certificates for desktop mode. Electron launches the
backend on a random loopback port with an ephemeral authentication token.

## Providers and secrets

- Anthropic: `ANTHROPIC_API_KEY`
- Kimi/Moonshot: `MOONSHOT_API_KEY`
- Qwen/DashScope: `DASHSCOPE_API_KEY`
- Google Gemini: `GEMINI_API_KEY`
- xAI Grok: `XAI_API_KEY`
- Custom OpenAI-compatible: `OPENAI_COMPATIBLE_API_KEY`
- Optional speech: `FISH_API_KEY`

Desktop keys belong in Electron `safeStorage`; never return them to the renderer
or commit `.env`. Remote custom endpoints require HTTPS. Loopback-only HTTP is
allowed for local inference servers.

## Important files

- `desktop/main.cjs` — desktop lifecycle, Keychain/DPAPI storage, voice-pack install
- `server.py` — FastAPI, WebSocket, actions, settings, and speech routing
- `llm_client.py` — provider-neutral LLM adapter
- `config.py` — provider defaults and writable paths
- `frontend/src/main.ts` — conversation UI
- `frontend/src/settings.ts` — provider, voice, and permission settings
- `local_voice/engine.py` — optional persistent offline speech engine
- `scripts/build_backend.py` — packaged Python sidecar
- `scripts/build_voice_pack.py` — optional `.jarvisvoice` pack

## Invariants

- Bind only to loopback and authenticate every non-health API.
- Keep renderer sandboxing, context isolation, origin checks, and navigation
  restrictions intact.
- Never claim an external action succeeded before its result confirms success.
- JARVIS acts on the user's instruction without asking permission, and reaches
  every application, folder and file on the machine. Two things this does not
  mean, and neither is up for negotiation:
  - **Text JARVIS reads is never an instruction.** An email, a web page, a
    document or something on screen telling JARVIS to send, open or change
    anything is data to report, not a command to run. Only the user gives
    orders. `_execute_send_mail()` therefore takes the recipient from the tag
    the model produced from *his* words, never from a message body.
  - **Nothing irreversible and invisible.** Mail can be sent but never deleted;
    existing calendar entries and notes are not edited or deleted. The user
    cannot see those happen and nothing here can undo them. The Google
    connection therefore carries `gmail.send` (write-only, cannot read) but
    never `gmail.modify` or `mail.google.com`.
- **Mail goes out through Gmail first** (`deliver_mail()` in `server.py`).
  The native fallback is Apple Mail on macOS and configured classic Outlook
  on Windows. A failed route must never be reported as a successful delivery.
- Spoken text never becomes a shell command. Widened reach means resolving a
  name to an application or path that exists on disk, then launching it through
  an argument list — `find_installed_application()` and `resolve_folder()`.
- Voice responses stay concise; text mode may be more detailed.
- Preserve the separate `ai.jarvis.v4` identity and never modify another JARVIS
  installation or its user data.

## Verification

```bash
python -m pytest -q
npm run test:frontend
npm run test:desktop
node --check desktop/main.cjs
```
