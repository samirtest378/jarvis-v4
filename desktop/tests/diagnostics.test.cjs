"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const { buildDiagnostics } = require("../diagnostics.cjs");

function fixture(overrides = {}) {
  return buildDiagnostics({
    appInfo: { version: "0.6.21", packaged: true },
    runtime: { platform: "darwin", arch: "arm64", osVersion: "15.5", backendRunning: true },
    backend: {
      healthy: true,
      version: "0.6.21",
      capabilities: { google_account_connected: true },
      llm_provider: "anthropic",
      llm_configured: true,
      llm_ready: true,
      env_keys_set: { anthropic: true },
      tts: {
        configured_provider: "auto",
        active_provider: "system",
        local_ready: false,
        fish_ready: false,
        system_available: true,
      },
      stt: { engine: "whisper.cpp", local: true, running: false },
    },
    storage: {
      mode: "keychain",
      secureStorageAvailable: true,
      hasKeychainSecrets: true,
      hasLocalSecrets: false,
    },
    access: {
      microphone: "granted",
      screen: "not-granted",
      files: "granted",
      accessibility: "not-granted",
      automation: { calendar: "unknown", mail: "unknown", notes: "unknown" },
    },
    voicePack: { installed: false, compatible: false },
    generatedAt: "2026-07-21T12:00:00.000Z",
    ...overrides,
  });
}

test("diagnostics contain useful health data and explicit privacy guarantees", () => {
  const report = fixture();
  assert.equal(report.schema, "jarvis-v4-diagnostics/v1");
  assert.equal(report.app.version, "0.6.21");
  assert.equal(report.accounts.google_connected, true);
  assert.equal(report.local_service.healthy, true);
  assert.equal(report.intelligence.provider, "anthropic");
  assert.equal(report.intelligence.ready, true);
  assert.equal(report.intelligence.provider_key_present, true);
  assert.equal(report.voice.recognition_engine, "whisper.cpp");
  assert.equal(report.voice.recognition_local, true);
  assert.equal(report.key_storage.protected_by_operating_system, true);
  assert.deepEqual(Object.values(report.privacy), [false, false, false, false, false]);
});

test("diagnostics never copy secrets, URLs, paths, names, conversations, or raw errors", () => {
  const markers = [
    "SUPER_SECRET_KEY",
    "token-in-custom-url",
    "/Users/private-person/Documents",
    "Private Person",
    "confidential conversation",
    "raw provider error",
  ];
  const report = fixture({
    backend: {
      healthy: true,
      version: "0.6.21",
      llm_provider: "custom",
      llm_configured: true,
      llm_ready: true,
      llm_base_url: "https://user:token-in-custom-url@example.invalid/v1",
      env_keys_set: { custom: true, raw: "SUPER_SECRET_KEY" },
      tts: { configured_provider: "fish", active_provider: "unavailable", fish_error: "raw provider error" },
      user_name: "Private Person",
      conversations: ["confidential conversation"],
    },
    storage: {
      mode: "local",
      secureStorageAvailable: true,
      hasLocalSecrets: true,
      rawKey: "SUPER_SECRET_KEY",
      path: "/Users/private-person/Documents",
    },
    voicePack: {
      installed: true,
      compatible: true,
      path: "/Users/private-person/Documents",
      error: "raw provider error",
    },
  });
  const serialized = JSON.stringify(report);
  for (const marker of markers) assert.equal(serialized.includes(marker), false, marker);
  assert.equal(report.intelligence.provider_key_present, true);
  assert.equal(report.voice.offline_pack_installed, true);
});

test("diagnostics normalize unexpected values instead of copying them", () => {
  const report = fixture({
    runtime: { platform: "secret-platform", arch: "secret-arch", osVersion: "X".repeat(200), backendRunning: 1 },
    backend: { healthy: "yes", llm_provider: "secret-provider", llm_configured: 1, env_keys_set: {} },
    access: { microphone: "secret-state", automation: {} },
  });
  assert.equal(report.system.platform, "unknown");
  assert.equal(report.system.architecture, "unknown");
  assert.equal(report.system.os_version.length, 96);
  assert.equal(report.local_service.running, false);
  assert.equal(report.local_service.healthy, false);
  assert.equal(report.intelligence.provider, "unknown");
  assert.equal(report.permissions.microphone, "unknown");
});
