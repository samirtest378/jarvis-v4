import assert from "node:assert/strict";
import test from "node:test";

import {
  audioPlaybackWatchdogMs,
  browserSpeechWatchdogMs,
  canExtendVoiceConversation,
  isFatalVoiceInputError,
  shouldSubmitSpeechWindow,
} from "../src/voice_activity.js";

test("submits a short command soon after speech ends", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 0.7 * 48000,
    sampleRate: 48000,
    voicedFrames: 6,
    voicedSamples: 0.30 * 48000,
    trailingSilenceFrames: 2,
    trailingSilenceSamples: 0.24 * 48000,
  }), true);
});

test("endpoint timing stays stable when the capture chunk size changes", () => {
  const base = {
    sampleCount: 0.8 * 48000,
    sampleRate: 48000,
    voicedSamples: 0.38 * 48000,
    trailingSilenceSamples: 0.23 * 48000,
  };
  assert.equal(shouldSubmitSpeechWindow({ ...base, voicedFrames: 4, trailingSilenceFrames: 3 }), true);
  assert.equal(shouldSubmitSpeechWindow({ ...base, voicedFrames: 9, trailingSilenceFrames: 6 }), true);
});

test("a natural word gap does not cut off the question", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 1.2 * 48000,
    sampleRate: 48000,
    voicedFrames: 12,
    voicedSamples: 0.6 * 48000,
    trailingSilenceFrames: 4,
    trailingSilenceSamples: 0.16 * 48000,
  }), false);
});

test("does not mistake a normal word gap for the end of a sentence", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 1.4 * 48000,
    sampleRate: 48000,
    voicedFrames: 6,
    trailingSilenceFrames: 1,
  }), false);
});

test("does not submit before a short utterance has enough context", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 0.5 * 48000,
    sampleRate: 48000,
    voicedFrames: 4,
    trailingSilenceFrames: 3,
  }), false);
});

test("does not cut a speaker off before the maximum window", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 8.2 * 48000,
    sampleRate: 48000,
    voicedFrames: 12,
    trailingSilenceFrames: 1,
  }), false);
});

test("bounds continuous speech so recognition still progresses", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 10.1 * 16000,
    sampleRate: 16000,
    voicedFrames: 15,
    trailingSilenceFrames: 0,
  }), true);
});

test("never sends silence or a single noise spike", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 5 * 48000,
    sampleRate: 48000,
    voicedFrames: 0,
    trailingSilenceFrames: 20,
  }), false);
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 5 * 48000,
    sampleRate: 48000,
    voicedFrames: 1,
    trailingSilenceFrames: 20,
  }), false);
});

test("accepts a short yes or ja after two voiced frames", () => {
  assert.equal(shouldSubmitSpeechWindow({
    sampleCount: 0.7 * 48000,
    sampleRate: 48000,
    voicedFrames: 2,
    trailingSilenceFrames: 2,
  }), true);
});

test("audio playback always has a bounded completion fallback", () => {
  assert.equal(audioPlaybackWatchdogMs(1.73), 2930);
  assert.equal(audioPlaybackWatchdogMs(Number.NaN), 1200);
  assert.equal(audioPlaybackWatchdogMs(300), 120000);
});

test("browser system speech has a bounded fallback for real answers", () => {
  assert.equal(browserSpeechWatchdogMs("Ja?"), 2500);
  assert.equal(browserSpeechWatchdogMs("This is a normal short reply."), 5400);
  assert.equal(browserSpeechWatchdogMs("word ".repeat(300)), 120000);
});

test("one failed transcription does not disable always-on listening", () => {
  assert.equal(isFatalVoiceInputError("Speech recognition failed"), false);
  assert.equal(isFatalVoiceInputError("The local engine timed out"), false);
  assert.equal(isFatalVoiceInputError("Microphone access denied. Please allow microphone access."), true);
  assert.equal(isFatalVoiceInputError("Microphone recording is unavailable on this computer."), true);
});

test("only a wake-started voice conversation may accept follow-up speech", () => {
  const base = {
    wakeEnabled: true,
    isMuted: false,
    voiceConversationActive: false,
    voiceReplyPending: false,
    wakeFollowupUntil: 0,
    now: 1000,
  };
  // Startup greeting or typed prompt.
  assert.equal(canExtendVoiceConversation(base), false);
  // A wake-started request is waiting for its spoken answer to finish.
  assert.equal(canExtendVoiceConversation({
    ...base,
    voiceConversationActive: true,
    voiceReplyPending: true,
  }), true);
  // A live follow-up window remains active, but an expired one does not.
  assert.equal(canExtendVoiceConversation({
    ...base,
    voiceConversationActive: true,
    wakeFollowupUntil: 1500,
  }), true);
  assert.equal(canExtendVoiceConversation({
    ...base,
    voiceConversationActive: true,
    wakeFollowupUntil: 999,
  }), false);
});
