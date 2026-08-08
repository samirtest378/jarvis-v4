/**
 * What the language setting means for the cloned JARVIS voice.
 *
 * V4 normally uses one compact NeuTTS pack for German and English. Legacy
 * upgrades can still contain MOSS or separate Chatterbox packs, so the copy
 * remains honest for every supported layout.
 */

/**
 * @param {{local_ready?: boolean, local_mode?: string, local_languages?: string[], bilingual_pack_installed?: boolean}} tts
 * @returns {string}
 */
export function voiceLanguageStateText(tts) {
  if (!tts || !tts.local_ready) {
    return "JARVIS voice pack not installed — the system voice speaks both languages.";
  }
  if ((tts.local_languages || []).includes("de")) {
    if (tts.local_mode === "neutts-nano") {
      return "Smooth JARVIS voice: German & English — the same V2-matched profiles on macOS, Windows, and Linux.";
    }
    if (tts.local_mode === "moss-nano") {
      return "Fast JARVIS voice: German & English — same cloned speaker, optimized for Apple Silicon.";
    }
    // Measured on this hardware: roughly a minute of work per spoken sentence,
    // so saying it is slow is a fact the user should see before choosing it.
    return "Legacy studio voice: German & English — same speaker, but slow to generate.";
  }
  return tts.bilingual_pack_installed
    ? "JARVIS voice: English only (fast). Choose Deutsch or Automatic for the German voice."
    : "JARVIS voice: English only — the German pack is not installed on this computer.";
}

/**
 * The pack a language setting selects, mirroring `_local_voice_pack_dir()` in
 * `server.py`. Kept here so the interface can explain the choice without
 * waiting for the backend to answer.
 *
 * @param {string} speechLanguage
 * @param {boolean} compactBilingual
 * @returns {"current" | "multilingual"}
 */
export function voicePackForLanguage(speechLanguage, compactBilingual = true) {
  if (compactBilingual) return "current";
  return String(speechLanguage || "auto").startsWith("en") ? "current" : "multilingual";
}
