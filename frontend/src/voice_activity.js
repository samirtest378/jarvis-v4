/**
 * Decide when a local microphone window contains a complete utterance.
 *
 * The local Whisper service works best with a little context, but waiting for
 * a fixed multi-second block makes short commands feel slow.  This helper ends
 * a window shortly after speech is followed by silence and retains a maximum
 * bound for people who speak without pausing.
 *
 * @param {{
 *   sampleCount: number,
 *   sampleRate: number,
 *   voicedFrames: number,
 *   voicedSamples?: number,
 *   trailingSilenceFrames: number,
 *   trailingSilenceSamples?: number,
 * }} state
 */
export function shouldSubmitSpeechWindow(state) {
  const sampleRate = Number.isFinite(state.sampleRate) && state.sampleRate > 0
    ? state.sampleRate
    : 16000;
  const seconds = Math.max(0, state.sampleCount) / sampleRate;
  // Two normal browser frames are roughly 170 ms. That catches short natural
  // replies such as "ja" and "yes"; the adaptive energy threshold still
  // rejects a single click or bump.
  const voicedSamples = Number(state.voicedSamples);
  const trailingSilenceSamples = Number(state.trailingSilenceSamples);
  const preciseDurations = Number.isFinite(voicedSamples)
    && Number.isFinite(trailingSilenceSamples);
  const hasSpeech = preciseDurations
    ? voicedSamples >= sampleRate * 0.12
    : state.voicedFrames >= 2;
  if (!hasSpeech) return false;

  // At the usual 48 kHz / 4096-sample browser buffer, two quiet frames are
  // about 170 ms. Combined with the adaptive voice threshold and retained
  // pre-roll this ends "ja", "yes", and short app commands promptly without
  // clipping their first or final consonant.
  const enoughTrailingSilence = preciseDurations
    ? trailingSilenceSamples >= sampleRate * 0.22
    : state.trailingSilenceFrames >= 2;
  const naturalEndpoint = seconds >= 0.55 && enoughTrailingSilence;
  // Long, natural questions must not be chopped into unrelated fragments.
  // Silence still submits short commands quickly; this upper bound exists only
  // for someone who speaks continuously without pausing.
  const boundedContinuousSpeech = seconds >= 10;
  return naturalEndpoint || boundedContinuousSpeech;
}

/**
 * Browser audio end events can be lost when macOS changes the active audio
 * device while the always-on microphone is open. Return a conservative
 * fallback deadline so the conversation can always resume.
 *
 * @param {number} durationSeconds
 * @returns {number}
 */
export function audioPlaybackWatchdogMs(durationSeconds) {
  const duration = Number.isFinite(durationSeconds) ? Math.max(0, durationSeconds) : 0;
  return Math.min(120000, Math.ceil(duration * 1000) + 1200);
}

/**
 * System speech has no decoded buffer duration available. Estimate a generous
 * deadline from word count so a lost browser `onend` cannot block wake mode.
 *
 * @param {string} text
 * @returns {number}
 */
export function browserSpeechWatchdogMs(text) {
  const words = String(text || "").trim().split(/\s+/u).filter(Boolean).length;
  return Math.min(120000, Math.max(2500, (words * 650) + 1500));
}

/**
 * Only device and permission failures should switch an always-on assistant
 * off. A single failed local transcription is transient and must recover.
 *
 * @param {string} message
 * @returns {boolean}
 */
export function isFatalVoiceInputError(message) {
  const normalized = String(message || "").toLocaleLowerCase();
  return (
    normalized.includes("microphone access denied")
    || normalized.includes("microphone recording is unavailable")
    || normalized.includes("speech recognition is unavailable")
    || normalized.includes("recording failed")
  );
}

/**
 * Decide whether finishing a reply may extend hands-free conversation mode.
 * Startup greetings and typed turns deliberately keep this false; only a
 * wake-started voice exchange owns the follow-up window.
 *
 * @param {{
 *   wakeEnabled: boolean,
 *   isMuted: boolean,
 *   voiceConversationActive: boolean,
 *   voiceReplyPending: boolean,
 *   wakeFollowupUntil: number,
 *   now: number,
 * }} state
 */
export function canExtendVoiceConversation(state) {
  if (!state.wakeEnabled || state.isMuted || !state.voiceConversationActive) return false;
  if (state.voiceReplyPending) return true;
  return state.wakeFollowupUntil > 0 && state.now <= state.wakeFollowupUntil;
}
