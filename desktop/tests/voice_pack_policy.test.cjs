const test = require("node:test");
const assert = require("node:assert/strict");
const {
  activateLocalVoicePreferences,
  envValue,
  selectActiveVoicePack,
  voicePackIdentity,
  voicePackSelectionMatches,
} = require("../voice_pack_policy.cjs");

test("the selected bundled voice supersedes an unmarked stale default", () => {
  assert.equal(selectActiveVoicePack({
    installedDirectory: "old",
    installedReady: true,
    bundledDirectory: "selected",
    bundledReady: true,
  }), "selected");
});

test("a fingerprinted manual voice remains an explicit user choice", () => {
  assert.equal(selectActiveVoicePack({
    installedDirectory: "custom",
    installedReady: true,
    installedCustom: true,
    bundledDirectory: "selected",
    bundledReady: true,
  }), "custom");
});

test("activation selects local voice but preserves text-only mode", () => {
  const local = activateLocalVoicePreferences("JARVIS_TTS_PROVIDER=system\n");
  assert.equal(envValue(local, "JARVIS_TTS_PROVIDER"), "local");
  const off = activateLocalVoicePreferences("JARVIS_TTS_PROVIDER=off\n");
  assert.equal(envValue(off, "JARVIS_TTS_PROVIDER"), "off");
});

test("voice selection markers are bound to profile hashes", () => {
  const manifest = { version: "4.1.1", files: { "profile-de.npy": "a".repeat(64) } };
  const record = { format_version: 1, source: "manual-install", ...voicePackIdentity(manifest) };
  assert.equal(voicePackSelectionMatches(record, manifest, "manual-install"), true);
  assert.equal(voicePackSelectionMatches(record, { ...manifest, files: { "profile-de.npy": "b".repeat(64) } }, "manual-install"), false);
});
