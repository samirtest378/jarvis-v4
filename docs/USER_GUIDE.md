# JARVIS v4 Quick User Guide

## Install on macOS

1. Open the downloaded DMG.
2. Drag **JARVIS v4** to **Applications**.
3. Open JARVIS v4 from Applications.
4. Complete the four setup steps and approve only the permissions you want.

Use only a Developer ID-signed and Apple-notarized installer whose SHA-256
checksum matches the seller's published checksum.

## Install on Windows

1. Open the signed `JARVIS-v4-<version>-x64.exe` download.
2. Follow the German/English installation assistant and choose the install
   folder.
3. Start **JARVIS v4** from the final page, Start Menu, or desktop shortcut.
4. Complete the same four setup steps shown on macOS.

A second shortcut launch restores the existing JARVIS window instead of
opening another app tab. Use only an Authenticode-signed installer whose seller
name and SHA-256 checksum match the published release information.

## Install on Linux

On Ubuntu, Debian, or Linux Mint, open the downloaded
`JARVIS-v4-<version>-x64.deb` with the Software app and choose **Install**. The
AppImage is a portable alternative: mark it executable in file properties and
open it directly. Both use the same JARVIS logo and restore the existing window
when launched a second time.

The DEB package includes `espeak-ng` as a local speech-output dependency. The
portable AppImage uses a speech engine already installed on the computer or an
optional JARVIS voice pack/provider selected in Settings. Private local JARVIS
notes work on Linux; Google can provide private Gmail metadata/instructed
sending and read-only Calendar events after connection.

## Speak naturally

- German: “Hey JARVIS, öffne meine E-Mails.”
- English: “Hey JARVIS, open my email.”

JARVIS answers a German request in German and an English request in English.
After the one-time microphone permission, a fresh Windows installation listens
for “Hey JARVIS” automatically; the main microphone button disables it at once.
Automatic recognition uses local CPU-only Whisper first and keeps microphone
audio on the computer. On Windows its process is limited to 2.5 GiB.

## Private accounts

Opening Gmail or Google Calendar in a browser does not give JARVIS access to
private account data. Private Gmail metadata and calendar events are available
only after the separate Google connection is completed. On Windows, configured
classic Outlook can instead provide local inbox and calendar access without a
separate JARVIS sign-in. New messages are sent only after a direct instruction.

## Read a public website safely

Give JARVIS a complete public HTTPS address, for example: “Lies
https://example.com und fasse die Seite zusammen.” JARVIS downloads only the
visible text with a read-only GET request. It does not use browser cookies,
logins, forms, uploads, or write requests, and it blocks local/private network
addresses and unsafe redirects. Instructions found inside a webpage are
treated as untrusted text and are never executed. Private or signed-in pages
must be opened by the user in the browser instead.

## API keys

Cloud providers require the customer's own API key. Never buy a copy containing
a shared seller API key. Never send an API key to customer support.

## Remove local data

Settings → Privacy & Reset contains **Delete all local JARVIS data**. This
removes local settings, keys, conversations, memories, tasks, notes, account
tokens, and installed voice packs after native confirmation.

External providers may retain data under their own policies; use the provider's
privacy controls to remove data held outside JARVIS.
