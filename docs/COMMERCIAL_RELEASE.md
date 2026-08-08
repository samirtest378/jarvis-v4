# JARVIS v4 Commercial Release Gate

This is the authoritative checklist for deciding whether a build may be sold.
Passing automated tests alone is not a commercial release approval.

## Current status

Version 4.1.2 has a polished desktop UI, private local service, optional cloud
API keys, a bundled multilingual Whisper engine for offline “Hey JARVIS” and
commands, a Windows-aware interface,
privacy-safe support diagnostics, an optional PKCE-protected Google account
connector, and an automated Windows x64 installer build. Release automation
uses a Windows-tested Python lock with exact
versions and package hashes, and installers embed a checksummed customer/legal
bundle covering the project terms, privacy, support, user guide, and collected
third-party license evidence. Its bundled native German/English voice pack uses separate, matched
language profiles, identical model weights, and deterministic mastering for the
same customer-provided voice identity on Windows, stays offline,
and rejects suspiciously truncated generations. Common
Windows apps and standard user folders are controlled through a
fixed allow-listed catalogue without arbitrary shell commands. German and
English wake commands are normalized for speech punctuation and route common
app, folder, screen, mail, calendar, task, and status requests without relying
on a cloud model. Ambiguous shortened speech such as “auf YouTube” can trigger
an action only when it follows a locally recognized wake phrase, and the
destination must still pass the fixed allow-list. The cloud-free system voice
has been exercised from the packaged WebSocket response, and Automatic voice
selection follows German, US English, or UK English instead of forcing one
accent. The four-step first-run flow now includes a dedicated permission review,
separates browser shortcuts from private Gmail/Calendar access, and never counts
a Windows-managed privacy state as confirmed access. It is **not
yet approved for sale** because the legal rights and production
signing evidence below are not complete.

## Blocking legal and brand gates

- [ ] Obtain a written commercial license from the upstream copyright owner.
  The repository `LICENSE` explicitly prohibits sale or other commercial use
  without a separate commercial license. Record the reviewed evidence in
  `docs/COMMERCIAL_LICENSE_CONFIRMATION.md`; do not commit confidential contract
  terms.
- [ ] Obtain a qualified trademark review for the product name, visual identity,
  and marketing. “JARVIS” and an MCU-style voice can create brand/personality
  rights risk even with a fan-project disclaimer. Record approval in
  `docs/BRAND_CLEARANCE_CONFIRMATION.md`.
- [ ] Confirm commercial rights for every logo, image, sound, voice reference,
  model, and voice pack. Record the scope and expiration in
  `docs/VOICE_RIGHTS_CONFIRMATION.md`.
- [ ] Have counsel review the customer EULA, refund terms, warranty disclaimer,
  privacy disclosure, consumer-rights text, and tax/VAT obligations for each
  sales region. Record the completed review, seller identity, and public privacy
  contact in `docs/PRIVACY_LEGAL_CONFIRMATION.md`.

## Product and privacy gates

- [x] No seller API key is embedded in source or installers.
- [x] Language intelligence defaults to OpenAI GPT-5.4 Nano and does not expose
  a local language-model download in the Windows product. Local CPU processing
  remains limited to speech recognition and the bundled selected voice.
- [x] No third-party character, celebrity, or public Fish voice reference is
  preconfigured; customers must explicitly enter a voice ID they are licensed
  to use.
- [x] Customer keys can use operating-system encryption or an explicit local
  file, and stored values are never returned to the renderer.
- [x] Backend is restricted to authenticated `127.0.0.1` access.
- [x] Renderer sandbox, context isolation, navigation restrictions, and explicit
  OS permission controls are enabled.
- [x] Windows replaces Apple-only Mail/Calendar rows with classic Outlook
  status and uses Windows-specific privacy and secret-storage language.
- [x] Windows uses native browser, terminal, File Explorer, window-listing, and
  on-request screen-capture paths without invoking macOS automation. Its fixed
  Outlook bridge reads inbox/calendar data and sends instructed mail through
  COM while all user content travels as JSON stdin, never PowerShell source.
  Private Calendar/Mail/Notes/Google data is never reported as read when no
  verified account integration exists.
- [x] Spoken app and folder commands use allow-listed platform targets. Unknown
  names and arbitrary paths are rejected rather than executed as commands.
- [x] Deterministic German/English voice routing covers core PC and approved
  account actions, including punctuation produced by bundled Whisper. The Voice
  panel exposes tested examples instead of requiring customers to guess syntax.
- [x] A repository privacy disclosure describes local storage and direct cloud
  provider requests.
- [x] Release builds compile a pinned, checksummed whisper.cpp engine and bundle
  a checksummed multilingual model. Audio is sent only to an authenticated
  localhost endpoint; the UI discloses when a system-service fallback is used.
- [ ] Replace the privacy contact placeholders with the seller's verified legal
  identity and contact details.
- [x] An in-app “Delete all local JARVIS data” flow uses a native confirmation,
  removes keys and private app data, clears renderer storage, and restarts.
  Windows uninstall also removes app data.
- [x] The in-app diagnostic report is generated from a strict allow-list and
  excludes keys, chats, memories, names, provider URLs, and personal paths.
- [x] Background window-title inspection is disabled by default; explicit
  screen requests remain available and the advanced opt-in is documented.
- [x] The Google connector uses a Desktop OAuth client, external system browser,
  S256 PKCE, random state, loopback-only callback, OS/private secret storage,
  Gmail metadata/send plus Calendar read-only scopes, and confirmed revocation
  on disconnect.
- [ ] Register the seller's production Google OAuth client, enable Gmail and
  Calendar APIs, complete brand/scope verification (and any security assessment
  Google requires), then record a real connect/read/disconnect test. Browser
  opening alone must not be advertised as private account access.

## Installer and signing gates

- [x] Windows x64 uses a German/English assisted NSIS installer with selectable
  destination, Start Menu/Desktop shortcuts, run-after-install, the same
  multi-resolution JARVIS logo, and private-data removal on uninstall.
- [x] Windows uses a stable app identity and a tested single-instance lock; a
  second launch restores the existing window and reuses its backend.
- [x] The bundled Windows recognizer uses Large-v3 Turbo Q8, rejects
  models over 1 GiB, and runs inside a hard 2.5 GiB process-memory ceiling.
- [x] CI builds the sale candidate on a native Windows x64 runner and refuses
  to publish an unsigned test installer.
- [x] The Windows installer stages and re-verifies its matching bilingual voice
  archive and pinned model/profile hashes.
- [x] CI rejects installers above GitHub's single-file 2 GiB limit, performs a
  clean silent install, verifies an in-place upgrade preserves private customer
  data, checks backend health and single-instance behavior, and uninstalls all
  private application data before a signed asset may be published.
- [ ] Configure an Authenticode OV/EV certificate or Azure Trusted Signing and
  verify the signature on the delivered Windows installer.
- [ ] Test install, upgrade, rollback, first launch, permissions, and uninstall
  on clean Windows 10 and Windows 11 x64 machines.
- [ ] Record a physical-microphone wake test in German and English on a typical
  Windows Intel laptop. Automated WAV transcription is necessary but cannot
  replace a human speaking into the target machine.
- [ ] Record clean-machine installation, first-run, upgrade, permission,
  German/English microphone, and uninstall evidence for the exact release
  artifacts in `docs/RELEASE_QA_CONFIRMATION.md`.
- [ ] Decide and document the update channel. Do not enable automatic updates
  until update packages are signed and hosted on a controlled HTTPS origin.

## Quality gate

Run before every candidate build:

```bash
npm run release:audit
npm run test:frontend
npm run test:desktop
python -m pytest -q
npm run build
npm run release:checksums
```

`npm run release:audit:strict` must pass before declaring the product ready for
sale. The strict check deliberately fails while legal/brand/voice confirmation
files are missing.

## CI secrets for signed releases

Use GitHub repository or environment secrets; never commit credentials:

- Windows signing: `WIN_CSC_LINK`, `WIN_CSC_KEY_PASSWORD`

Run the **Build JARVIS v4 installers** workflow in `signed` mode to create a
candidate; that workflow never publishes. After physical QA, record the exact
installer SHA-256 in the signing and QA confirmations. The separate publisher
runs the strict commercial audit, rechecks Authenticode, matches both recorded
hashes to the downloaded installer, repeats the Windows smoke test, verifies
the source workflow run and only then creates or updates the GitHub release.
