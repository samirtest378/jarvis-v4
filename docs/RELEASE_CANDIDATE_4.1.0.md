# JARVIS v4.1.0 Engineering Release Candidate

Date: 30 July 2026

This file records technical evidence for the current Apple Silicon candidate.
It is not a legal or commercial release approval.

## Five critical improvements

1. Answers prioritize factual accuracy, reject false premises, and avoid
   inventing actions, sources, dates, or system state.
2. Each turn is scored independently for German or English. Explicit language
   requests win, and a clearly wrong-language answer is regenerated once.
3. Automatic speech recognition uses the higher-quality cloud route first when
   configured, with local multilingual Whisper as a private fallback.
4. Voice interaction ends natural utterances sooner, keeps follow-up listening
   bounded, and selects the best available German or English system locale.
5. Local voice generation chooses the most natural-duration candidate instead
   of blindly returning the final failed attempt.

## Automated evidence

- Python: 415 passed, 7 skipped.
- Frontend: 40 passed; production TypeScript/Vite build passed.
- Desktop: 27 passed.
- Source release audit: passed with human/legal blockers reported separately.
- npm production audit: 0 known vulnerabilities in the desktop and frontend
  production dependency trees.
- Python dependency audit: 0 known vulnerabilities in the resolved runtime
  dependency tree.
- Reproducibility: a universal macOS/Windows Python lock with exact versions and
  distribution hashes installed successfully in a clean Python 3.11
  environment.
- Compliance bundle: 62 third-party components and 94 customer/license files
  were collected, checksummed, and embedded in the application. The Help menu
  opens the user guide, privacy disclosure, support page, and license manifest.
- Release automation: the stale JARVIS v3 workflow/artifact names were replaced
  with JARVIS v4-only names.
- Installed macOS app: nested code signature structure verifies successfully.
- Runtime: one installed `/Applications/JARVIS v4.app` instance and one private
  loopback backend were observed. An unauthenticated health request was rejected
  with HTTP 401 as designed.

## Candidate artifacts

- `JARVIS-v4-4.1.0-arm64.dmg`
- `JARVIS-v4-4.1.0-arm64.zip`
- `JARVIS-v4-Smooth-Bilingual-Voice-4.1.0-darwin-arm64.jarvisvoice`
- `JARVIS-v4-4.1.0-SHA256SUMS.txt`

Use the checksum file beside these artifacts to verify the exact bytes.

Current SHA-256 values:

- DMG: `d009e64044b611f45d4ad678364e63afd2db96c5eab31dd3402025edc3f6c39b`
- ZIP: `02122abe3fc2e57541a81bef2914d34bf86becb08864c89a5ab591c09dc1fde6`
- Voice pack: `77d6653af3f85d981ebb6568526c93c6271f49c79bca3507688d91f58cc57dd1`

## Commercial blockers

The candidate must not be advertised or sold until the strict release audit
passes. At minimum this requires verified evidence for the upstream commercial
license, brand/trademark clearance, all voice and reference-audio rights,
privacy/customer-terms review and seller contact, Apple Developer ID signing
and notarization, and clean-machine release QA.

The current macOS artifact is ad-hoc signed for local testing. Its code
structure verifies, but Gatekeeper distribution assessment does not pass
without a real Developer ID signature and Apple notarization.
