/**
 * Parse a wake phrase only at the beginning of a transcript.
 * Phonetic aliases cover common local-STT spellings without letting a casual
 * mention later in a sentence authorize a command.
 *
 * @param {string} text
 * @returns {{matched: boolean, command: string}}
 */
export function parseWakeCommand(text) {
  const normalized = text.trim();
  const match = normalized.match(/^(?:(?:hey|hei|hel|her|hi|hallo|hello|okay|ok)[\s,.:;!?-]*)?(?:jarvis|jervis|jarviss|javis|jarves|travis|charvis|scharvis|tscharvis|dscharvis|gravis|grabis|brabis)\b[\s,.:;!?-]*(.*)$/i);
  return match ? { matched: true, command: match[1].trim() } : { matched: false, command: "" };
}

/** @param {string} text */
export function isWakeFragment(text) {
  return /^(?:hey|hei|hel|her|hi|hallo|hello|okay|ok|jarvis|jervis|jarviss|javis|jarves|travis|charvis|scharvis|tscharvis|dscharvis|gravis|grabis|brabis)[\s.!?,;:-]*$/i.test(text.trim());
}
