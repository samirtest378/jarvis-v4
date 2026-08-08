const GERMAN_MARKERS = new Set([
  "aber", "auch", "auf", "bitte", "das", "dein", "der", "die", "ein", "eine",
  "erledigt", "fertig", "für", "genau", "gern", "gerne", "gut", "hallo", "ich",
  "ist", "ja", "kann", "klar", "machen", "mein", "mit", "moment", "natürlich",
  "nicht", "noch", "oder", "richtig", "sicher", "sofort", "soll", "und",
  "verstanden", "von", "was", "wie", "wir", "zu", "bereit", "danke",
]);
const ENGLISH_MARKERS = new Set([
  "a", "also", "and", "are", "can", "certainly", "correct", "do", "done", "for",
  "hello", "how", "i", "in", "is", "it", "my", "not", "of", "on", "or",
  "please", "ready", "sure", "thanks", "that", "the", "this", "to",
  "understood", "we", "welcome", "what", "with", "yes", "you", "your",
]);

/**
 * Resolve automatic speech output from the answer itself. This lets one
 * conversation switch naturally between German and English without changing
 * a setting or sending voice text to another service.
 *
 * @param {string} text
 * @param {string} configured
 * @returns {string}
 */
export function inferSpeechLanguage(text, configured = "auto") {
  const selected = String(configured || "").trim();
  if (/^de(?:-|$)/i.test(selected)) return "de-DE";
  if (/^en(?:-|$)/i.test(selected)) return /^en-US$/i.test(selected) ? "en-US" : "en-GB";

  const normalized = String(text || "").toLocaleLowerCase();
  if (/[äöüß]/u.test(normalized)) return "de-DE";
  const words = normalized.match(/\p{L}+/gu) || [];
  let german = 0;
  let english = 0;
  for (const word of words) {
    if (GERMAN_MARKERS.has(word)) german += 1;
    if (ENGLISH_MARKERS.has(word)) english += 1;
  }
  if (german > english) return "de-DE";
  if (english > german) return "en-GB";

  const system = typeof navigator !== "undefined" ? String(navigator.language || "") : "";
  return system.toLowerCase().startsWith("de") ? "de-DE" : "en-GB";
}

/**
 * Choose the system voice used for short spoken confirmations.
 *
 * Three things have to hold, in this order:
 *   1. The spoken language must match the answer so German never arrives with
 *      an English accent (and vice versa).
 *   2. A voice the user picked explicitly wins within that language.
 *   3. Within that language, a JARVIS-style masculine voice is preferred when
 *      the operating system provides one.
 *   4. With automatic recognition the language is not known in advance, so
 *      fall back to the language the computer is set to rather than to
 *      whichever voice happens to come first in the list.
 *
 * @param {SpeechSynthesisVoice[]} voices
 * @param {string} language
 * @param {string} [preferredName] the configured system voice, if any
 * @returns {SpeechSynthesisVoice | null}
 */
export function selectBrowserSpeechVoice(voices, language, preferredName = "") {
  let normalized = String(language || "").toLowerCase();
  if (!normalized || normalized === "auto") {
    const system = typeof navigator !== "undefined" ? navigator.language : "";
    normalized = String(system || "en-GB").toLowerCase();
  }
  const prefix = normalized.split("-", 1)[0];

  const named = String(preferredName || "").trim();
  if (named && named.toLowerCase() !== "auto") {
    const exact = voices.find((voice) => voice.name === named);
    const exactLanguage = String(exact?.lang || "").toLowerCase().replace("_", "-");
    if (
      exact
      && (exactLanguage === normalized || exactLanguage === prefix || exactLanguage.startsWith(`${prefix}-`))
    ) {
      return exact;
    }
  }

  // Masculine voices shipped with Windows and macOS, best first. Windows voice
  // names vary between classic SAPI and Chromium, so keep the exact common
  // names and still fall back by language when another pack is installed.
  /** @type {Record<string, string[]>} */
  const MASCULINE = {
    de: [
      "Microsoft Stefan - German (Germany)",
      "Microsoft Conrad Online (Natural) - German (Germany)",
      "Microsoft Conrad - German (Germany)",
      "Markus", "Yannick", "Viktor",
      "Eddy (Deutsch (Deutschland))", "Flo (Deutsch (Deutschland))",
      "Reed (Deutsch (Deutschland))", "Rocko (Deutsch (Deutschland))",
    ],
    en: [
      "Microsoft George - English (United Kingdom)",
      "Microsoft Ryan Online (Natural) - English (United Kingdom)",
      "Microsoft Guy Online (Natural) - English (United States)",
      "Daniel", "Oliver", "Alex", "Arthur",
    ],
    fr: ["Thomas"],
    es: ["Jorge"],
    it: ["Luca"],
  };
  for (const name of MASCULINE[prefix] || []) {
    const match = voices.find((voice) => voice.name === name);
    if (match) return match;
  }

  const sameLanguage = voices.find((voice) => voice.lang.toLowerCase() === normalized)
    || voices.find((voice) => voice.lang.toLowerCase().startsWith(`${prefix}-`));
  if (sameLanguage) return sameLanguage;

  // If the requested language is unavailable, keep the assistant character
  // before falling back to an arbitrary platform voice.
  for (const names of Object.values(MASCULINE)) {
    for (const name of names) {
      const match = voices.find((voice) => voice.name === name);
      if (match) return match;
    }
  }

  return voices.find((voice) => voice.default) || voices[0] || null;
}
