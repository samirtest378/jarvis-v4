"use strict";

const ALLOWED_ACCESS_STATES = new Set([
  "granted", "denied", "restricted", "not-determined", "not-granted",
  "limited", "unavailable", "unknown",
  "available", "managed",
]);

function accessState(value) {
  return ALLOWED_ACCESS_STATES.has(value) ? value : "unknown";
}

function plainBoolean(value) {
  return value === true;
}

function safeLabel(value, allowed, fallback = "unknown") {
  return allowed.includes(value) ? value : fallback;
}

/**
 * Build a deliberately allow-listed support snapshot. Never spread source
 * objects here: backend responses, manifests, environment variables and error
 * objects may contain credentials, URLs, file paths or user content.
 */
function buildDiagnostics({ appInfo, runtime, backend, storage, access, voicePack, generatedAt }) {
  const backendTts = backend?.tts || {};
  const backendStt = backend?.stt || {};
  const backendKeys = backend?.env_keys_set || {};
  return {
    schema: "jarvis-v4-diagnostics/v1",
    generated_at: typeof generatedAt === "string" ? generatedAt : new Date().toISOString(),
    app: {
      name: "JARVIS v4",
      version: String(appInfo?.version || "unknown").slice(0, 64),
      packaged: plainBoolean(appInfo?.packaged),
    },
    system: {
      platform: safeLabel(runtime?.platform, ["darwin", "win32", "linux"]),
      architecture: safeLabel(runtime?.arch, ["arm64", "x64", "ia32"]),
      os_version: String(runtime?.osVersion || "unknown").slice(0, 96),
    },
    local_service: {
      running: plainBoolean(runtime?.backendRunning),
      healthy: plainBoolean(backend?.healthy),
      version: String(backend?.version || "unknown").slice(0, 64),
    },
    intelligence: {
      provider: safeLabel(backend?.llm_provider, ["ollama", "openai", "anthropic", "kimi", "qwen", "gemini", "grok", "custom"]),
      configured: plainBoolean(backend?.llm_configured),
      ready: plainBoolean(backend?.llm_ready),
      provider_key_present: plainBoolean(backendKeys[backend?.llm_provider]),
    },
    accounts: {
      google_connected: plainBoolean(backend?.capabilities?.google_account_connected),
    },
    voice: {
      configured_provider: safeLabel(backendTts.configured_provider, ["auto", "openai", "local", "fish", "system", "off"]),
      active_provider: safeLabel(backendTts.active_provider, ["openai", "local", "fish", "system", "unavailable"]),
      local_ready: plainBoolean(backendTts.local_ready),
      fish_ready: plainBoolean(backendTts.fish_ready),
      system_available: plainBoolean(backendTts.system_available),
      offline_pack_installed: plainBoolean(voicePack?.installed),
      offline_pack_compatible: plainBoolean(voicePack?.compatible),
      recognition_engine: safeLabel(backendStt.engine, ["whisper.cpp", "system-fallback"]),
      recognition_local: plainBoolean(backendStt.local),
      recognition_running: plainBoolean(backendStt.running),
    },
    key_storage: {
      mode: safeLabel(storage?.mode, ["keychain", "local"]),
      protected_by_operating_system: storage?.mode === "keychain" && plainBoolean(storage?.secureStorageAvailable),
      secure_storage_available: plainBoolean(storage?.secureStorageAvailable),
      saved_key_in_secure_storage: plainBoolean(storage?.hasKeychainSecrets),
      saved_key_in_private_local_file: plainBoolean(storage?.hasLocalSecrets),
    },
    permissions: {
      microphone: accessState(access?.microphone),
      screen_capture: accessState(access?.screen),
      files: accessState(access?.files),
      accessibility: accessState(access?.accessibility),
      calendar: accessState(access?.automation?.calendar),
      mail: accessState(access?.automation?.mail),
      notes: accessState(access?.automation?.notes),
    },
    privacy: {
      contains_api_keys: false,
      contains_conversations: false,
      contains_memory_or_tasks: false,
      contains_personal_file_paths: false,
      contains_user_name: false,
    },
  };
}

module.exports = { buildDiagnostics };
