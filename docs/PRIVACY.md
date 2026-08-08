# JARVIS v4 Privacy Disclosure

Last updated: 8 August 2026

This disclosure describes the behavior of the desktop application in this
repository. A seller must replace the support/contact placeholders and obtain
legal review for the countries in which the product is offered before public
distribution.

## Plain-language summary

JARVIS v4 runs its interface, local service, memory, automation, bundled
German/English speech recognition, and bundled voice on the user's computer.
On a fresh Windows installation, microphone recognition and speech output stay
local and CPU-only. Cloud speech remains an explicit optional setting. The app
has no built-in advertising, analytics, or telemetry. Language intelligence
uses the cloud provider selected by the user. When a user selects a cloud language-model or voice
provider, information needed for that request is sent directly from the app to
the selected provider using the user's own API key.

## Data stored on the computer

The app may store:

- provider settings and encrypted API keys, or keys in the explicitly selected
  unencrypted private local-file mode;
- an optional Google Desktop OAuth client configuration and refresh token in
  the same selected secret store;
- conversation memory, tasks, notes, preferences, and local usage records;
- the optional offline voice pack; and
- operating-system permission state managed by macOS, Windows, or Linux.

Electron stores these files in the user's normal application-data directory:

- macOS: `~/Library/Application Support/jarvis-v4-desktop/`
- Windows: `%APPDATA%\jarvis-v4-desktop\`
- Linux: `~/.config/jarvis-v4-desktop/`

Managed installations may redirect configuration and data with
`JARVIS_CONFIG_DIR` and `JARVIS_DATA_DIR`.

## Data sent to other services

JARVIS sends data only when a user enables or requests a feature that needs an
external service:

- A selected language-model provider receives the prompt and the context that
  JARVIS assembles for that request. This may include conversation text or
  requested task context.
- Fish Audio receives the text submitted for speech synthesis when Fish Audio
  voice is selected.
- Speech recognition is set to **Automatic** by default, which uses bundled
  CPU-only Whisper first. Short microphone windows travel only to the
  authenticated loopback service and stay on the computer. A configured
  OpenAI or Fish speech service is tried only if local recognition is
  unavailable; selecting either cloud provider explicitly also sends audio to
  that provider. Windows enforces a hard 2.5 GiB limit on the recognizer.
- The bundled JARVIS voice speaks locally on the CPU. Text is sent to OpenAI or
  Fish Audio for speech generation only when the user explicitly selects that
  cloud voice provider.
- Websites opened by the user or through an explicit automation request receive
  the normal data a browser sends to those websites.
- When the user explicitly asks JARVIS to read a public HTTPS page, the
  read-only reader sends a GET request without browser cookies, credentials,
  forms, uploads, or write methods. It blocks local/private network addresses,
  non-standard ports, unsafe redirects, non-text responses, and oversized
  pages. The extracted page text and the user's question are sent to the
  selected language-model provider to produce the answer. Text found on the
  page is treated as untrusted data and cannot authorize a computer action.
- When Google is connected, JARVIS sends the refresh token to Google's token
  endpoint and uses the returned short-lived access token only with the Gmail
  and Calendar APIs. It requests Gmail metadata (sender, subject, and date) and
  permission to send a new message after an explicit instruction, plus
  read-only Calendar events. It does not request Gmail body, modify/delete
  existing mail, or Calendar write scopes. The content of a requested outgoing
  message is sent to Gmail only to deliver that message.
- Screen capture is performed only after an explicit request by default. An
  advanced desktop background window-title mode exists but remains disabled
  unless the user explicitly enables `JARVIS_BACKGROUND_SCREEN_CONTEXT=1`.

Those providers process data under their own terms and privacy policies.
JARVIS does not proxy the requests through a seller-controlled server in the
current architecture.

## API keys

The recommended mode protects keys with Electron `safeStorage`, backed by the
macOS Keychain, Windows DPAPI, or a supported Linux secret store. The optional
local-file mode avoids operating-system password prompts but is not encrypted.
The renderer can submit a new key but cannot read a stored key back.

Users should revoke a key immediately if it is pasted into a chat, issue,
screen recording, or log. Seller-owned shared API keys must not be embedded in
the app or installer.

## Permissions and computer access

JARVIS does not bypass operating-system security. Microphone, screen capture,
Accessibility, Calendar, Mail, Notes, and file access remain controlled by the
user and the operating system. Apple application automation is available only
on macOS. On Windows, configured classic Outlook is accessed locally through
its COM object model; JARVIS reads inbox/calendar data on explicit request and
sends only a newly instructed message. Dictated content is passed as JSON over
standard input and is never inserted into PowerShell source. Opening Gmail or
Google Calendar in a browser does not grant private access. The optional Google
connector uses a separate consent screen, PKCE, state validation, a
loopback-only callback, Gmail metadata/send scopes, and a read-only Calendar
scope. JARVIS can
perform powerful actions after permission is granted, so users should enable
only the integrations they need.

## Retention and deletion

Local data remains until the user deletes it. The Windows installer is
configured to remove JARVIS application data during uninstall. On macOS, a user
can remove the application-data directory after quitting the app. Removing
local data does not delete information already processed by an external
provider; users must use that provider's privacy controls for external data.
Disconnecting Google from Settings first attempts to revoke the grant, then
removes its local OAuth credentials and token after native confirmation.

## Contact

Before sale, replace this section with the legal business name, support email,
privacy contact, and applicable company address.
