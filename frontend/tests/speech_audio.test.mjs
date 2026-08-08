import assert from "node:assert/strict";
import test from "node:test";

import { floatToPcmWav, resampleSpeech } from "../src/speech_audio.js";

function tone(frequency, sampleRate, seconds, amplitude = 0.5) {
  const output = new Float32Array(Math.floor(sampleRate * seconds));
  for (let index = 0; index < output.length; index++) {
    output[index] = amplitude * Math.sin(2 * Math.PI * frequency * index / sampleRate);
  }
  return output;
}

function rms(samples) {
  let total = 0;
  for (const value of samples) total += value * value;
  return Math.sqrt(total / samples.length);
}

test("high-quality microphone resampling preserves the speech band", () => {
  const input = tone(1000, 48000, 0.5);
  const output = resampleSpeech(input, 48000, 16000);

  assert.equal(output.length, 8000);
  assert.ok(rms(output) > 0.30);
});

test("microphone resampling rejects energy above Whisper's Nyquist band", () => {
  const aliasedInput = tone(12000, 48000, 0.5);
  const output = resampleSpeech(aliasedInput, 48000, 16000);

  assert.ok(rms(output) < 0.025);
});

test("speech WAV encoder emits 16 kHz mono PCM", () => {
  const wav = floatToPcmWav(tone(500, 44100, 0.25), 44100);
  const view = new DataView(wav);

  assert.equal(String.fromCharCode(...new Uint8Array(wav, 0, 4)), "RIFF");
  assert.equal(String.fromCharCode(...new Uint8Array(wav, 8, 4)), "WAVE");
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(24, true), 16000);
  assert.ok(Math.abs((wav.byteLength - 44) / 2 - 4000) <= 1);
});
