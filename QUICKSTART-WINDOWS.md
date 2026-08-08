# JARVIS v4 — Windows Quick Start

## Install

1. Download the signed `JARVIS-v4-<version>-x64.exe` installer.
2. Open it. The German/English installation assistant lets you select the user
   account and installation folder.
3. Leave **Run JARVIS v4** selected on the final page, or start it later from
   the Start Menu or desktop shortcut.

Opening the shortcut again restores the existing JARVIS window; it does not
start a second assistant, backend, or app tab. The installer, executable,
taskbar window, shortcuts, and uninstaller all use the same JARVIS v4 logo.

For a public sale build, Windows must show the verified seller name in the
signature details. Do not distribute an installer that displays “Unknown
publisher.”

## First setup

1. Open **Settings → Intelligence**.
2. For private local AI, install Ollama and select **Local AI · Ollama**. JARVIS
   can start a stopped service, detect installed models, select an available
   model, and verify a real local reply before setup continues. No API key is
   required. JARVIS can install the balanced Qwen model when Ollama is present.
3. Alternatively select OpenAI, Anthropic, Kimi, Qwen, Gemini, Grok, or a custom
   compatible endpoint.
4. Keep **Windows encryption — recommended** selected.
5. Paste your own provider key when using a cloud provider, choose **Test
   provider**, then **Save & restart**.
6. The installer already contains the same bilingual JARVIS voice used on the
   Mac build. English uses the reference-video profile; German uses the
   selected V3 Tuned 1 German profile. Open **Voice** only if you want to change it.
7. If the seller has supplied a verified Google Desktop OAuth client, open
   **System → Google Account**, enter its client ID, and choose **Connect
   Google**. It can read Gmail metadata, send only on your command, and read
   Calendar events through the normal system-browser consent flow.

JARVIS never needs a seller-owned shared API key. Every customer should use a
key from their chosen provider or local Ollama.

The installer includes multilingual offline Whisper recognition for the wake
phrase and spoken commands. Enable **“Hey JARVIS” on startup**, choose German
or English, and run **Run voice check**. The microphone button always shows
when listening and stops capture immediately when switched off.
The included Large-v3 Turbo Q8 recognizer is capped at 2.5 GiB of process memory
on Windows (and in Linux builds); replacement models above 1 GiB are rejected
before loading.
The Windows installer also includes the verified NeuTTS voice model and the
same English/German profiles used by macOS, so no second voice download is
required.

Voice capture runs in Chromium's dedicated audio thread instead of the window
thread, so animation and Windows compositing cannot drop microphone frames.
Whisper and NeuTTS choose a bounded CPU pool and run below the interactive UI
priority: they retain fast local inference while leaving capacity for the
JARVIS animation, audio playback, and the rest of Windows. Background
throttling is disabled only while JARVIS is actively listening and resumes as
soon as the microphone session ends.

Useful hands-free commands include “Open YouTube”, “Open Gmail”, “Start
Spotify”, “Open Settings”, “Show Downloads”, and “Open my Documents folder”.
Apps and folders come from a safe built-in catalogue; spoken text is never run
as an unrestricted Windows command.

## Computer access

Open **Settings → Access** to review microphone and file permissions. Windows
privacy controls remain in charge; JARVIS cannot bypass them. When classic
Outlook is installed and configured, JARVIS can read its inbox and today's
calendar and can send a new message only after your explicit instruction. The
fixed Outlook bridge does not insert dictated text into PowerShell commands.
As an alternative, private Gmail metadata/instructed sending and read-only
Calendar events become available after the verified Google consent flow.

## Remove private data

Use **Settings → System → Privacy & Reset → Delete all local JARVIS data** to
remove keys, memory, tasks, preferences, and the offline voice pack. A native
confirmation appears before deletion. The Windows uninstaller is also
configured to remove JARVIS application data.

## Troubleshooting

- If a provider test fails, confirm the provider, model, billing/credits, and
  key permissions in that provider's dashboard.
- If Windows SmartScreen shows “Unknown publisher,” the installer is an
  unsigned test build and is not suitable for sale.
- If voice input is unavailable, open **Windows Settings → Privacy & security →
  Microphone** and allow desktop apps to use the microphone.
