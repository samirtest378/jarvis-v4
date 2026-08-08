# JARVIS v4 on macOS — quick start

1. Open `JARVIS-v4-0.6.21-arm64.zip`, unzip it, and drag **JARVIS v4.app** into
   **Applications**.
2. The first time, Control-click **JARVIS v4** in Applications, choose **Open**,
   then confirm **Open**.
3. In JARVIS v4, open **Settings → Language Model**.
4. For a fully local setup, choose **Local AI · Ollama**. JARVIS checks the
   runtime, starts a stopped local service when requested, detects installed
   models, and selects a working model. Choose **Next: Voice**; the setup tests
   and saves a real local reply before continuing. No API key is needed. If no
   model is available, JARVIS can install the balanced Qwen model from this screen.
5. Alternatively choose OpenAI, Anthropic, Kimi, Qwen, Gemini, Grok, or Custom; paste
   that provider's API key; select **Test provider**; then select **Save & restart**.

To connect Gmail and Google Calendar, the seller must first supply a verified
Google Desktop OAuth client. Open **Settings → System → Google Account**, enter
that client ID, and select **Connect Google**. JARVIS requests read-only Calendar
events and Gmail sender/subject/date metadata; it does not request message-body,
send, modify, or delete permission.

Under **Key storage**, choose **Local file — no Mac password** if you cannot
approve the macOS Keychain dialog. This private file is readable only by your
user account but is not encrypted, so Keychain remains the safer option.
Environment variables remain available when no key was saved in the app.
An OpenAI/Anthropic/Kimi/Qwen/Gemini/Grok key controls the written answers only; it is
not a speech key. Voice uses the local pack, Fish Audio, or the built-in Mac
voice separately.

## Voice

The normal installer includes multilingual offline Whisper recognition. In
**Settings → Voice & Animation**, leave **“Hey JARVIS” on startup** enabled,
choose German or English, then select **Run voice check**. The app displays
what it heard locally and verifies an audible reply. macOS asks
for microphone permission on first use; the red microphone button stops and
releases the microphone immediately.

Useful hands-free commands include “Open YouTube”, “Öffne Mail”, “Starte
Spotify”, “Öffne Einstellungen”, “Zeige Downloads”, and “Öffne meinen
Dokumente-Ordner”. JARVIS uses a fixed safe catalogue for apps and standard
folders; unknown names are not turned into Terminal commands.

The installer already contains the native bilingual JARVIS reference voice.
Leave the provider on **Automatic** or choose **Smooth JARVIS voice**, then
select **Test voice**. The system voice remains an immediate fallback if the
larger local engine cannot start safely.

If macOS exposes a system voice but returns an empty audio file, JARVIS v4 now
switches to its local built-in Mac/Chromium speech fallback automatically.

Speech is generated locally after installation; no Fish Audio key or second
voice download is required. A separately downloaded `.jarvisvoice` file is
needed only for an upgrade or a development build.

For the hosted Fish voice, open **Settings → Voice & Animation**, use **Get a
Fish key**, paste that separate key, and select **Test**. The test now generates
and plays a real sample before **Save Fish** stores the key. Enter a Fish Voice
ID that you created or are licensed to use commercially; no third-party
character or celebrity reference is bundled. Requests use Fish Audio's current
`s2-pro` model header. A Fish account needs available credits. Follow the voice
owner's permissions and Fish Audio's terms.

## If a provider does not connect

- Make sure the selected provider matches the key. OpenAI and Anthropic keys do
  not work with Gemini, Kimi, Qwen, or Grok.
- Select **Test provider** before saving. JARVIS v4 reports whether the key,
  model, quota, or endpoint is the problem without displaying the secret.
- If a key was ever pasted into a public chat, revoke it in the provider console
  and create a new one before adding it to JARVIS v4.

For development, cross-platform builds, environment variables, and the complete
security model, see `README.md`.
