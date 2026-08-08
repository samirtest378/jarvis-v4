"use strict";

const crypto = require("node:crypto");

function selectActiveVoicePack({ installedDirectory = "", installedReady = false, installedCustom = false, bundledDirectory = "", bundledReady = false } = {}) {
  if (installedReady && installedCustom) return installedDirectory;
  if (bundledReady) return bundledDirectory;
  return installedReady ? installedDirectory : "";
}

function voicePackIdentity(manifest) {
  const safe = manifest && typeof manifest === "object" ? manifest : {};
  const files = safe.files && typeof safe.files === "object" ? safe.files : {};
  const identity = {
    version: typeof safe.version === "string" ? safe.version : "",
    voice_identity: typeof safe.voice_identity === "string" ? safe.voice_identity : "",
    engine_mode: typeof safe.engine_mode === "string" ? safe.engine_mode : "",
    profile_en: typeof files["profile-en.npy"] === "string" ? files["profile-en.npy"] : "",
    profile_de: typeof files["profile-de.npy"] === "string" ? files["profile-de.npy"] : "",
    profile_default: typeof files["profile.pt"] === "string" ? files["profile.pt"] : "",
    profile_safetensors: typeof files["profile.safetensors"] === "string" ? files["profile.safetensors"] : "",
    profile_safetensors_de: typeof files["profile-de.safetensors"] === "string" ? files["profile-de.safetensors"] : "",
    profiles_metadata: typeof files["profiles.json"] === "string" ? files["profiles.json"] : "",
  };
  return { ...identity, fingerprint: crypto.createHash("sha256").update(JSON.stringify(identity)).digest("hex") };
}

function voicePackSelectionMatches(record, manifest, source) {
  if (!record || typeof record !== "object" || record.format_version !== 1 || record.source !== source) return false;
  const identity = voicePackIdentity(manifest);
  return record.version === identity.version && record.fingerprint === identity.fingerprint;
}

function envValue(contents, key) {
  const pattern = new RegExp(`^${key}=([^\\r\\n]*)$`, "gm");
  let value = "";
  for (const match of String(contents || "").matchAll(pattern)) value = match[1].trim();
  return value;
}

function setEnvValue(contents, key, value) {
  let updated = String(contents || "");
  const pattern = new RegExp(`^${key}=[^\\r\\n]*$`, "gm");
  if (pattern.test(updated)) return updated.replace(pattern, `${key}=${value}`);
  if (updated && !updated.endsWith("\n")) updated += "\n";
  return `${updated}${key}=${value}\n`;
}

function activateLocalVoicePreferences(contents, { forceLocal = false } = {}) {
  let updated = String(contents || "");
  if (forceLocal || envValue(updated, "JARVIS_TTS_PROVIDER").toLowerCase() !== "off") {
    updated = setEnvValue(updated, "JARVIS_TTS_PROVIDER", "local");
  }
  return setEnvValue(updated, "JARVIS_VOICE_PACK", "current");
}

module.exports = { activateLocalVoicePreferences, envValue, selectActiveVoicePack, setEnvValue, voicePackIdentity, voicePackSelectionMatches };
