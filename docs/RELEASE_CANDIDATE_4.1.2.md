# JARVIS v4.1.2 Windows Engineering Release Candidate

This Windows-focused patch release keeps the verified German and English voice
identity and strengthens the local CPU speech path, settings, permissions,
installer verification and commercial release controls.

## User-visible improvement

- German and English Q4 backbones are loaded lazily and retained in one
  private voice process during a conversation.
- The language inferred from the user's turn is warmed while the cloud model
  prepares the answer.
- Deutsch → English → Deutsch no longer reloads and discards 186 MB weights on
  every language change.
- Voice helpers without the optional warmup protocol remain compatible.

## Verified invariants

- The production German and English profile hashes are unchanged.
- The verified German and English profiles, inference seeds and reference-video
  mastering remain unchanged. Recompiled native runtimes can produce different
  WAV bytes while preserving that voice identity.
- Both cached backbones used approximately 1.27 GB RSS on the Apple-Silicon
  release test machine.
- The new frozen helper advertised and completed `warm-language-cache` for
  German and English.
- Local speech recognition remains independently capped at 2,560 MB on Windows.
- Windows voice synthesis and recognition are CPU-only by default, so the
  integrated GPU remains available to the desktop and background animation.

## Automated verification

- Test counts must be copied from the final clean release run; historical counts
  are not accepted as evidence.
- The release workflow builds only the Windows x64 installer.
- A native Windows smoke test verifies install, in-place upgrade, bundled local
  DE/EN voice, Whisper and Silero VAD, health, single-instance behavior and
  clean uninstall.
- Publication requires a valid Authenticode signature and a strict commercial
  audit bound to the exact installer SHA-256.

## Release order

1. Build the Windows x64 voice pack and installer on the native Windows runner.
2. Verify the bundled profiles, CPU runtimes and installer contents.
3. Sign the installer and require a valid Authenticode result.
4. Run the full install, upgrade, launch, single-instance and uninstall smoke
   test against the signed installer.
5. Bind Windows 10/11 manual QA and all commercial confirmations to that exact
   installer SHA-256.
6. Publish one customer-facing `.exe` only after the strict audit passes.

Commercial sale remains blocked until the human confirmations listed in
`docs/COMMERCIAL_RELEASE.md` are completed.
