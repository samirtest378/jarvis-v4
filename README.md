# JARVIS v4

JARVIS v4 is the independent successor to v3. It keeps the secure Electron /
FastAPI architecture and adds a compact bilingual cloned voice based on
NeuTTS Nano, llama.cpp, and ONNX Runtime. V3 can remain archived as a separate
backup without appearing as an installed application.

JARVIS v4 is a voice- and text-first personal AI assistant packaged as a real
cross-platform Electron desktop application. It keeps the original FastAPI
automation, memory, planning, macOS integrations, and reactive Three.js orb,
while adding a complete conversation UI, secure settings, multiple language
model providers, and an optional fully local reference-derived voice.

The desktop application owns the app ID `ai.jarvis.v4` and its own user-data
directory. It can therefore coexist with a different JARVIS installation
without sharing its settings, keys, databases, or voice pack.

Mac users who only want to install and use the app can follow
[`QUICKSTART-MAC.md`](QUICKSTART-MAC.md); no development setup is required.
Windows users can follow [`QUICKSTART-WINDOWS.md`](QUICKSTART-WINDOWS.md).
Linux users can follow [`QUICKSTART-LINUX.md`](QUICKSTART-LINUX.md).

## What is included

- Standalone macOS, Windows, and Linux desktop shell
- Anthropic Claude, Kimi/Moonshot, Qwen/DashScope, Google Gemini, xAI Grok,
  keyless local Ollama, and custom
  OpenAI-compatible language-model connections
- Selectable secret storage: OS-encrypted Electron `safeStorage` (macOS
  Keychain, Windows DPAPI, or a supported Linux secret store), or a
  password-free private local file
- Environment variables for managed deployments and development
- Text chat, visible conversation history, cloud speech input with the bundled
  multilingual whisper.cpp engine as an offline fallback, a local “Hey JARVIS”
  wake phrase, and multiple speech-output fallbacks
- Compact bilingual NeuTTS voice bundled with integrity validation and the same
  German/English JARVIS profiles and mastering on macOS, Windows, and Linux;
  legacy packs remain supported
- Authenticated local FastAPI service on a random `127.0.0.1` port
- One-instance-per-profile lock so settings and the heavyweight voice engine
  cannot be split across competing desktop processes
- The supplied cyan particle-network artwork as the JARVIS v4 app icon and
  in-app brand mark, plus an animated orb with the classic visualization kept
  as a selectable backup
- Existing memory, tasks, research, Calendar, Mail, Notes, screen, browser, and
  Claude Code workflows retained
- Fast, model-independent voice shortcuts for common websites, allow-listed
  native apps, standard user folders, screen checks, and approved Gmail/Calendar
  reads in German and English; Whisper punctuation is normalized, while unknown
  app names and arbitrary paths are never executed as system commands
- Explicit read-only access to public HTTPS pages without browser cookies,
  credentials, forms, uploads, write methods, or local/private network access;
  page instructions are isolated as untrusted text
- Optional Google Desktop OAuth connection using PKCE and operating-system
  secret storage for Gmail metadata/instructed sending and read-only Calendar events

## Requirements

For development:

- Python 3.11 or newer
- Node.js 20 or newer
- CMake for release builds (the pinned offline speech engine is compiled per OS)
- Ollama for keyless local AI, a key for any supported cloud provider, or a
  reachable custom OpenAI-compatible endpoint
- macOS 14+, Windows 10+, or a modern Linux distribution

Fish Audio, Claude Code, and Playwright are optional. The release installers
already contain the native offline JARVIS voice pack. Apple Calendar/Mail/Notes automation remains macOS-specific; Windows
gets equivalent local mail and calendar access through configured classic
Outlook, while JARVIS's own notes work on every platform. Browser/app/folder
opening, native terminal launching, screen capture on explicit request, core
chat, and the desktop UI work on macOS, Windows, and Linux.

## Google account connection

JARVIS can connect a Google account through the system browser using the
installed-app OAuth flow with PKCE. It requests Gmail metadata
(sender/subject/date, not message bodies), permission to send a new message
only when instructed, and read-only Calendar events. The
refresh token remains in the same OS-encrypted or explicit private local store
as the user's provider keys and is never returned to the renderer.

The seller must create a **Desktop app** OAuth client, enable the Gmail and
Google Calendar APIs, configure the consent screen, and complete Google's
required verification before selling this feature. Enter the desktop client ID
and optional supplied client secret under **Settings → System → Google
Account**, then select **Connect Google**. The OAuth listener binds to a random
`127.0.0.1` port, validates `state`, uses an S256 PKCE verifier, and closes after
the callback. See Google's [desktop OAuth guide](https://developers.google.com/identity/protocols/oauth2/native-app),
[Gmail scope rules](https://developers.google.com/workspace/gmail/api/auth/scopes),
and [Calendar scope rules](https://developers.google.com/workspace/calendar/api/auth).

## Development setup

```bash
git clone https://github.com/NotKhoa03/jarvis-secure.git jarvis-v4
cd jarvis-v4

python3.11 -m venv .venv
source .venv/bin/activate             # Windows: .venv\Scripts\activate
python -m pip install --require-hashes -r requirements-build.lock.txt

npm run setup
npm run dev
```

Open **Settings → Language Model**, select a provider, enter its key, and choose
**Save & restart**. JARVIS tests the proposed provider before committing the
change. The desktop renderer can submit a new key but can never read it back.
An explicit in-app save replaces an inherited environment value; environment
variables remain the fallback for managed installations with no saved key.
Choose **Local file — no Mac password** to prevent all Keychain access. JARVIS
stores the value as `secrets.local.json` in its private user-data directory
with mode `0600` on POSIX systems. This is convenient but not encrypted: other
software already running as the same OS user may be able to read it. The
Keychain option remains recommended when its password is available.

## Language-model providers

| Provider | Default base URL | Default chat model | Key variable |
| --- | --- | --- | --- |
| Local AI · Ollama | `http://127.0.0.1:11434/v1` | `qwen3.5:9b` | none |
| OpenAI | `https://api.openai.com/v1` | `gpt-5.4-nano` | `OPENAI_API_KEY` |
| Anthropic | native Messages API | `claude-sonnet-5` | `ANTHROPIC_API_KEY` |
| Kimi / Moonshot | `https://api.moonshot.ai/v1` | `kimi-k2.6` | `MOONSHOT_API_KEY` |
| Qwen / DashScope | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` | `qwen3.7-plus` | `DASHSCOPE_API_KEY` |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | `gemini-3.6-flash` | `GEMINI_API_KEY` |
| xAI Grok | `https://api.x.ai/v1` | `grok-4.3` | `XAI_API_KEY` |
| Custom | configurable | configurable | `OPENAI_COMPATIBLE_API_KEY` |

OpenAI, Kimi, Qwen, Gemini, and Grok use their official OpenAI-compatible APIs. The
Qwen URL is editable so a matching regional Model Studio endpoint can be used.
Key-creation and model references: [OpenAI API](https://developers.openai.com/api/docs/),
[Kimi API](https://platform.kimi.ai/docs/),
[Qwen Model Studio](https://help.aliyun.com/en/model-studio/model-calling-in-sub-workspace),
[Gemini models](https://ai.google.dev/gemini-api/docs/models), and
[xAI models](https://docs.x.ai/developers/models).
For managed installations, `KIMI_API_KEY`, `QWEN_API_KEY`, `GOOGLE_API_KEY`,
and `GROK_API_KEY` are accepted aliases for the corresponding Moonshot,
DashScope, Gemini, and Grok keys. OpenAI and custom-compatible endpoint keys
remain separate so selecting one provider can never silently reuse the other.
Keys pasted with
surrounding quotes, a `Bearer ` / `Authorization: Bearer ` prefix, or as a full
`export NAME=value` line are normalized before a request is sent.
Custom remote endpoints must use HTTPS; plain HTTP is deliberately accepted
only for `localhost`, `127.0.0.1`, or `::1`. Credentials embedded in a URL,
query strings, and fragments are rejected.

Example environment-only Kimi configuration:

```bash
export JARVIS_LLM_PROVIDER=kimi
export MOONSHOT_API_KEY="your-key"
export JARVIS_MODEL=kimi-k2.6
npm run dev
```

Example local OpenAI-compatible configuration:

The desktop Settings panel also includes a dedicated **Local AI · Ollama**
choice. It detects installed models from `http://127.0.0.1:11434/v1`, needs no
API key, and defaults to `qwen3.5:9b` for a practical speed/quality balance.
On first launch JARVIS separately verifies the Ollama runtime, running service,
and selected model instead of treating configuration as readiness. If Ollama is
installed but stopped, **Start local AI** launches a JARVIS-managed local service
without forwarding any cloud API secrets. If another compatible model is already
installed, the setup selects it and verifies a real reply before continuing.
The current model sizes and tags are documented in the
[official Ollama Qwen 3.5 library](https://ollama.com/library/qwen3.5/tags).

```bash
export JARVIS_LLM_PROVIDER=custom
export JARVIS_LLM_BASE_URL=http://127.0.0.1:1234/v1
export JARVIS_MODEL=local-model
npm run dev
```

## Complete configuration

| Variable | Purpose |
| --- | --- |
| `JARVIS_LLM_PROVIDER` | `ollama`, `openai`, `anthropic`, `kimi`, `qwen`, `gemini`, `grok`, or `custom` |
| `JARVIS_LLM_BASE_URL` | OpenAI-compatible base URL; not used by Anthropic |
| `JARVIS_MODEL` | Main/chat model name |
| `JARVIS_RESEARCH_MODEL` | Deeper research model name |
| `JARVIS_OLLAMA_EXECUTABLE` | Optional explicit path to an installed Ollama CLI |
| `OPENAI_API_KEY` | OpenAI credential |
| `ANTHROPIC_API_KEY` | Anthropic credential |
| `MOONSHOT_API_KEY` | Kimi/Moonshot credential |
| `DASHSCOPE_API_KEY` | Qwen/DashScope credential |
| `GEMINI_API_KEY` | Google Gemini credential |
| `XAI_API_KEY` | xAI Grok credential |
| `OPENAI_COMPATIBLE_API_KEY` | Optional custom-endpoint bearer token |
| `FISH_API_KEY` | Optional Fish Audio speech credential |
| `FISH_VOICE_ID` | Optional Fish Audio voice reference ID |
| `JARVIS_TTS_PROVIDER` | `auto`, `local`, `fish`, `system`, or `off` |
| `JARVIS_SYSTEM_VOICE` | Offline OS voice; `Auto` follows the selected language |
| `JARVIS_SPEECH_LANGUAGE` | Recognition, system-voice, and cloned-voice language (`auto`, `de-DE`, `en-US`, or `en-GB`) |
| `JARVIS_WAKE_ENABLED` | Persist “Hey JARVIS” across app restarts (`0` or `1`) |
| `JARVIS_VOICE_PACK` | Which installed pack the cloned voice uses: `auto` (recommended), `current` (compact bilingual v4 pack), or `multilingual` (legacy pack) |
| `JARVIS_SYSTEM_SPEECH_RATE` | Offline speech rate from 90 to 260 |
| `USER_NAME` / `HONORIFIC` | How JARVIS v4 addresses the user |
| `CALENDAR_ACCOUNTS` | Comma-separated Apple Calendar accounts |
| `JARVIS_AUTH_TOKEN` | Fixed local token for browser/server mode |
| `JARVIS_CONFIG_DIR` | Writable `.env` and preference directory |
| `JARVIS_DATA_DIR` | Writable databases and usage-data directory |
| `JARVIS_LOCAL_VOICE_PACK` | Development path to an unpacked voice pack |
| `JARVIS_LOCAL_VOICE_START_TIMEOUT` | Max seconds to wait for the local voice engine (default 300, max 900) |
| `JARVIS_LOCAL_VOICE_SYNTH_TIMEOUT` | Max seconds to wait for one local utterance (default 180, max 900) |
| `JARVIS_SPEECH_RUNTIME` | Development override for the bundled whisper.cpp directory |
| `JARVIS_WHISPER_SERVER` / `JARVIS_WHISPER_MODEL` | Development overrides for the speech executable/model |
| `JARVIS_STT_PROVIDER` | Recognition route: `auto` (cloud first), `openai`, `fish`, `local`, `off` |
| `JARVIS_STT_MODEL` | Cloud transcription model (default `gpt-4o-mini-transcribe`, falls back to `whisper-1`) |

Copy `.env.example` to `.env` for server-only development. Never commit `.env`.
Configuration files created by the backend receive user-only permissions on
platforms that support POSIX modes.

## Voice options

Voice input is local-first and separate from speech output. Release builds
compile a pinned whisper.cpp server and bundle the multilingual
`ggml-large-v3-turbo-q8_0` model. The renderer records short mono PCM windows, sends them only to the
authenticated FastAPI service on `127.0.0.1`, and receives text. The model stays
loaded while listening, so each phrase does not pay startup cost. If the local
runtime is absent in a development build, Settings explicitly reports the
operating-system/Chromium fallback, which may require its provider's network
service. Oversized replacement models are rejected. Windows places the
recognizer in a 2.5 GiB process-memory job, and Linux applies the same hard
ceiling with an operating-system process limit.

`auto` selects speech in this order:

1. OpenAI speech when an OpenAI key is configured;
2. Fish Audio with an explicitly configured, licensed reference;
3. the operating system's immediate local voice;
4. an installed offline JARVIS voice pack.

Select **Smooth JARVIS voice** explicitly to use the V4 bilingual NeuTTS pack.
If it cannot start or finish safely, the renderer falls back to the system
voice instead of leaving the answer silent.

Fish Audio uses `POST https://api.fish.audio/v1/tts` with the current `s2-pro`
model header. In **Settings → Voice & Animation**, **Test** makes a real request
and plays the returned sample; a successful new key is then stored using the
selected Keychain or password-free local mode. No third-party character or
celebrity voice reference is preconfigured. Enter a Fish Voice ID that you
created or are licensed to use commercially. Create a separate speech key in the
[Fish Audio API Keys dashboard](https://fish.audio/app/api-keys/). A language
model key cannot be used for speech. Fish Audio requires available credits;
follow the voice owner's permissions and Fish Audio's terms for your use case.

Every macOS, Windows, and Linux installer includes its native verified
`.jarvisvoice` contents, so the voice identity, bilingual profiles, model
weights, and mastering match immediately. Small numerical differences between
CPU and CUDA inference are possible. Standalone voice-pack files remain
available for upgrades and development builds. V4's compact pack contains NeuTTS Nano,
the selected V3 old-reference English profile and V3 Tuned 1 German profile;
the older MOSS and Chatterbox packs remain supported. Activate another pack through
**Settings → Voice & Animation → Activate Existing Voice Pack**.
The desktop app extracts it in a private directory, rejects unsafe archive
paths and symbolic links, enforces size limits, validates platform and CPU
compatibility, and checks every manifest SHA-256 value before activating it.

On macOS, the built-in `say` voice is converted from AIFF to browser-compatible
PCM WAV automatically. This matters in Electron because Web Audio does not
reliably decode AIFF. Empty or undecodable system-audio output is rejected and
the desktop UI falls back to Chromium's local macOS speech synthesizer instead
of reporting silent playback. The compact V4 engine uses llama.cpp and ONNX
Runtime, stays warm
during active conversation, and releases its memory after 30 idle minutes.
Legacy Chatterbox packs may still take several minutes to start; tune the bounded waits
with `JARVIS_LOCAL_VOICE_START_TIMEOUT` (default 300 seconds) and
`JARVIS_LOCAL_VOICE_SYNTH_TIMEOUT` (default 180 seconds) for a slower machine.
Both values are capped at 15 minutes.

Generate a real WAV sample from an unpacked pack:

```bash
python scripts/synthesize_voice_sample.py \
  --pack-dir /absolute/path/to/unpacked-pack \
  --output JARVIS-v4-sample.wav
```

Build the preferred bilingual pack with a prepared NeuTTS runtime and
PyInstaller:

```bash
python scripts/build_voice_pack.py \
  --mode neutts-nano \
  --model-dir /path/to/neutts-runtime-models \
  --profile /path/to/profile-en.npy \
  --profile-de /path/to/profile-de.npy \
  --profile-metadata /path/to/profiles.json \
  --output-dir release
```

The compact profile is derived from the user-provided reference recording; the
source audio is not bundled. Reference-conditioned synthesis is not guaranteed
to be a mathematically identical copy of a speaker. Only use audio for which
you have the necessary permission, and do not use generated speech deceptively.

## Build installers

The build compiles a pinned, checksummed whisper.cpp runtime, verifies and
bundles its multilingual model, compiles the Vite interface, freezes the
FastAPI backend as a PyInstaller sidecar, and packages everything with Electron.
Run it on each target OS:

```bash
source .venv/bin/activate
npm run build
```

Artifacts are written to `release/`: DMG and ZIP on macOS, NSIS on Windows, and
AppImage/DEB on Linux. Use `npm run build:dir` for a faster unpacked app build.
Public macOS distribution requires your own Developer ID signing identity and
Apple notarization; local ad-hoc builds can be opened manually for testing.
The automated installer workflow builds native Apple Silicon, Intel Mac,
Windows x64, and Linux x64 artifacts. Signed/tag builds intentionally fail when the required
Apple or Windows certificate secrets are missing. See
[`docs/COMMERCIAL_RELEASE.md`](docs/COMMERCIAL_RELEASE.md) for the release gate
and [`docs/PRIVACY.md`](docs/PRIVACY.md) for the product privacy disclosure.
Platform setup is covered in [`QUICKSTART-MAC.md`](QUICKSTART-MAC.md),
[`QUICKSTART-WINDOWS.md`](QUICKSTART-WINDOWS.md), and
[`QUICKSTART-LINUX.md`](QUICKSTART-LINUX.md).

## Security design

- The backend binds only to `127.0.0.1`.
- Electron generates a random 256-bit bearer token per app session.
- REST authentication uses a header; WebSocket authentication uses a negotiated
  subprotocol, keeping credentials out of URLs and logs.
- Context isolation and renderer sandboxing are enabled; Node.js integration is
  disabled, navigation is restricted, and privileged desktop calls verify the
  renderer origin.
- API keys are never returned by a status endpoint. Keychain mode uses
  operating-system encryption; password-free mode uses an explicitly selected
  private local file and never invokes the Keychain decryptor. If Linux exposes
  only Electron's insecure `basic_text` backend, Keychain-mode persistence is
  refused while the clearly labelled local mode remains available.
- The app never grants itself OS access. macOS consent remains under
  **Settings → System Access** and System Settings.
- Screen capture happens only after an explicit screen request by default.
  Optional background window-title context is off unless an advanced user sets
  `JARVIS_BACKGROUND_SCREEN_CONTEXT=1`.
- Use **Check & Request** to ask for microphone access and test Calendar, Mail,
  Notes, screen capture, Accessibility, and user-folder access. macOS may still
  require a manual approval in Privacy & Security; no desktop app can safely or
  legitimately bypass those user-controlled prompts.
- Use **Privacy & Reset → Delete all local JARVIS data** to remove saved keys,
  memory, tasks, preferences, browser storage, usage records, and the installed
  offline voice pack after a native confirmation.
- Google disconnect uses a native confirmation, revokes the grant with Google,
  removes the local OAuth credentials and refresh token, and restarts the
  private backend.

The assistant can intentionally launch tools and automate approved apps. Review
the permissions before enabling those workflows, and never expose its service
to a network interface.

## Browser-only mode

```bash
source .venv/bin/activate
npm ci --prefix frontend
npm run build --prefix frontend
python server.py
```

The first server run writes `JARVIS_AUTH_TOKEN` to `.env` with private file
permissions. Desktop mode is recommended because its token is ephemeral and is
never placed in browser storage.

## Architecture

```text
Electron main process
  ├─ Keychain-encrypted or password-free private local provider keys
  ├─ random localhost port + session token
  ├─ Python/PyInstaller FastAPI sidecar
  └─ sandboxed Chromium renderer
       ├─ Vite + TypeScript conversation UI
       ├─ Three.js reactive orb
       └─ authenticated REST + WebSocket

FastAPI
  ├─ native Anthropic or OpenAI-compatible provider adapter
  ├─ persistent local whisper.cpp speech recognition
  ├─ local / Fish / system speech chain
  ├─ SQLite memory, tasks, notes, and usage data
  └─ optional macOS application bridges
```

## Tests

```bash
source .venv/bin/activate
python -m pytest -q
npm run test:frontend
npm run test:desktop
node --check desktop/main.cjs
node --check desktop/preload.cjs
```

Network/browser integration tests skip when their optional browsers or services
are not installed. Live API tests remain opt-in and are not part of normal
pytest runs.

## Troubleshooting

- **A key was pasted into a chat, issue, or log:** revoke it immediately in the
  provider console and create a replacement. Never reuse an exposed key.
- **Provider test fails:** JARVIS v4 distinguishes authentication, billing,
  permission/model, endpoint, rate-limit, and connection failures in Settings.
  Paste the replacement key, select the matching provider, choose **Test
  provider**, then **Save & restart**.
- **The voice-pack file exists but voice is unavailable:** having a
  `.jarvisvoice` archive is not the same as activating it. Select the file from
  Voice & Animation. The repaired installer accepts the official 6,325-file
  pack while retaining its 8-GB cap, path checks, platform check, and per-file
  SHA-256 validation.
- **Smooth JARVIS voice is unavailable:** verify that the selected pack reports
  `neutts-nano`, German + English, and `APPLE-ACCELERATE` in System Health. V4 bounds
  compact-engine startup and synthesis waits, falls back to the system voice,
  and reports the last local error. Legacy multi-gigabyte packs keep their
  longer compatibility timeouts.
- **The test says it is playing but there is no sound:** run Test Voice after
  clicking inside the app once to satisfy macOS/Electron autoplay rules. The
  test reports browser decoder and playback errors; system voice output is sent
  as WAV rather than AIFF for reliable decoding.

## License and credits

The existing project license remains in [`LICENSE`](LICENSE). whisper.cpp's MIT
license is bundled beside its executable. Third-party local voice notices are
in [`local_voice/THIRD_PARTY_NOTICES.md`](local_voice/THIRD_PARTY_NOTICES.md)
and inside each pack. JARVIS v4 is an independent fan project and is not
affiliated with Marvel Entertainment, The Walt Disney Company, Anthropic,
Moonshot AI, Alibaba Cloud, Google, xAI, Fish Audio, or Resemble AI.
