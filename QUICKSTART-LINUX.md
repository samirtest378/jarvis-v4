# JARVIS v4 — Linux Quick Start

## Install

For Ubuntu, Debian, Linux Mint, or another Debian-based system, download the
`JARVIS-v4-<version>-x64.deb` file and open it with the system's Software app.
Choose **Install**, then start **JARVIS v4** from the application menu.

The portable `JARVIS-v4-<version>-x64.AppImage` needs no installation. Mark it
as executable in the file properties and open it. Both packages use the same
JARVIS v4 logo and opening JARVIS again focuses the existing window instead of
starting another assistant or tab.

## First setup

1. Open **Settings → Intelligence** and select the existing OpenAI Nano setup,
   another supported provider, or local Ollama.
2. Open **Voice** and keep recognition on **Automatic** or **On this computer**.
3. Select **Automatic — German & English** so JARVIS answers German in German
   and English in English.
4. Run **Run voice check** and allow microphone access if the desktop asks.
5. Connect Google in **System** if private Gmail metadata, instructed sending,
   and read-only Google Calendar events are wanted.

The installer contains the same multilingual Large-v3 Turbo Q8 Whisper model
as Windows and macOS. On Linux, its recognition process has a hard 2.5 GiB
memory ceiling and releases the loaded model after 30 idle minutes when
hands-free listening is off.

Both Linux packages contain the same bilingual JARVIS profiles, NeuTTS model
weights, and crisp mastering as macOS and Windows, with a native Linux engine.
The DEB package also installs `espeak-ng` as an immediate fallback. The
AppImage carries the pronunciation runtime used by the JARVIS voice itself.

## Linux capabilities

- Open safe, installed apps, websites, and standard folders.
- Open the installed desktop environment's System Settings directly.
- Understand German and English speech locally.
- Use private local JARVIS tasks, memories, and notes.
- Capture the screen on explicit request when `gnome-screenshot`, `spectacle`,
  or `scrot` is installed and the desktop grants access.
- Use private Gmail metadata/sending and read-only Google Calendar after the
  verified Google connection.

Apple Mail, Apple Calendar, Apple Notes, and classic Outlook automation are
platform-specific and are hidden on Linux. JARVIS never treats opening Gmail in
a browser as permission to read private account data.

## Remove private data

Use **Settings → System → Privacy & Reset → Delete all local JARVIS data** before
uninstalling if saved keys, account tokens, conversations, memories, notes, and
voice packs should be removed.

## Troubleshooting

- If the AppImage does not open, enable **Allow executing file as program** in
  its file properties.
- If voice input is unavailable, allow microphone access for JARVIS in the
  desktop privacy settings.
- If screen understanding is unavailable, install the screenshot tool used by
  the desktop environment.
- If the local voice cannot start, run **Test voice** to see the exact status;
  JARVIS falls back to the system voice instead of leaving the answer silent.
