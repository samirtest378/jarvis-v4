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
  // 120 ms catches short replies such as "ja" and "yes" while still
  // rejecting a single click or bump.
  const voicedSamples = Number(state.voicedSamples);
  const trailingSilenceSamples = Number(state.trailingSilenceSamples);
  const preciseDurations = Number.isFinite(voicedSamples)
    && Number.isFinite(trailingSilenceSamples);
  const hasSpeech = preciseDurations
    ? voicedSamples >= sampleRate * 0.12
    : state.voicedFrames >= 2;
  if (!hasSpeech) return false;

  // About 320 ms tolerates a natural thinking pause in German and English.
  const enoughTrailingSilence = preciseDurations
    ? trailingSilenceSamples >= sampleRate * 0.32
    : state.trailingSilenceFrames >= 7;
  const naturalEndpoint = seconds >= 0.55 && enoughTrailingSilence;
  // Long, natural questions must not be chopped into unrelated fragments.
  // Silence still submits short commands quickly; this upper bound exists only
  // for someone who speaks continuously without pausing.
  const boundedContinuousSpeech = seconds >= 15;
  return naturalEndpoint || boundedContinuousSpeech;
}

/**
 * Classify a microphone block without learning immediate speech as noise.
 * @param {{rms: number, noiseFloor: number, calibrationFrames: number, speechStarted: boolean}} state
 * @returns {{voiced: boolean, noiseFloor: number, calibrationFrames: number}}
 */
export function classifySpeechFrame(state) {
  const rms = Number.isFinite(state.rms) ? Math.max(0, state.rms) : 0;
  let noiseFloor = Number.isFinite(state.noiseFloor)
    ? Math.max(0.0015, Math.min(0.08, state.noiseFloor))
    : 0.004;
  const calibrationFrames = Math.max(0, Math.floor(state.calibrationFrames || 0));
  const calibrating = calibrationFrames < 6;
  const speechStarted = state.speechStarted === true;
  const multiplier = speechStarted ? 1.30 : calibrating ? 1.40 : 1.80;
  const minimum = calibrating ? 0.006 : 0.0045;
  const threshold = Math.max(minimum, Math.min(0.18, noiseFloor * multiplier));
  const voiced = rms > threshold;

  if (!voiced && !speechStarted) {
    const boundedRms = Math.max(0.0015, Math.min(0.08, rms));
    const weight = calibrating ? 0.35 : 0.03;
    noiseFloor = (noiseFloor * (1 - weight)) + (boundedRms * weight);
  }
  return {
    voiced,
    noiseFloor,
    calibrationFrames: calibrating ? calibrationFrames + 1 : calibrationFrames,
  };
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
