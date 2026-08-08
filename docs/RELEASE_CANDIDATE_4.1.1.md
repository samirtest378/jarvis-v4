# JARVIS v4.1.1 Engineering Release Candidate

This patch release keeps the verified 4.1.0 German and English profiles,
generation settings, mastering chain, UI and security model. It replaces only
the native NeuTTS helper and related backend coordination.

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
- Local speech recognition remains independently capped at 2,560 MB on Windows
  and Linux.

## Automated verification

- Python: 487 passed, 1 skipped
- Frontend: 54 passed; production TypeScript/Vite build passed
- Desktop: 40 passed
- Native macOS arm64 and Intel x64 voice archives built and staged successfully
- Intel x64 helper synthesized German speech and completed the DE → EN → DE
  warm-cache protocol under Rosetta
- macOS native dependencies are bounded to the documented macOS 14+ baseline
- Release automation inspects every Mach-O file and rejects a native dependency
  whose deployment target is newer than macOS 14
- The compact PyInstaller helper excludes unused ONNX conversion, benchmark,
  quantization and transformer tooling: both Mac archives lost 320 files and
  about 14 MB without changing the deterministic German verification WAV.
- The slim Apple-Silicon helper cached both backbones at about 1.05 GB maximum
  resident memory in the release exercise.

## Release order

1. Create private draft release `v4.1.1` without publishing its tag.
2. Build and upload the macOS arm64, macOS x64, Linux x64 and Windows x64 voice
   packs to that draft.
3. Verify every voice archive and profile hash.
4. Publish/tag `v4.1.1`; the tag starts native installer jobs that consume only
   4.1.1 voice packs.
5. Verify installer hashes and clean-machine behavior before offering them to
   customers.

Commercial sale remains blocked until the human confirmations listed in
`docs/COMMERCIAL_RELEASE.md` are completed.
