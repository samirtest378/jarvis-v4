/** Prepare browser microphone audio for Whisper's 16 kHz input. */

/** @param {Float32Array} samples @param {number} sampleRate @returns {Float32Array} */
function highPass(samples, sampleRate) {
  const output = new Float32Array(samples.length);
  const cutoff = 65;
  const dt = 1 / sampleRate;
  const rc = 1 / (2 * Math.PI * cutoff);
  const alpha = rc / (rc + dt);
  let previousInput = 0;
  let previousOutput = 0;
  for (let index = 0; index < samples.length; index++) {
    const input = Number.isFinite(samples[index]) ? samples[index] : 0;
    const value = alpha * (previousOutput + input - previousInput);
    output[index] = value;
    previousInput = input;
    previousOutput = value;
  }
  return output;
}

/**
 * Windowed-sinc resampling avoids folding laptop fan noise and consonant
 * harmonics into Whisper's speech band. The previous three-sample average was
 * quick, but it was only a weak anti-alias filter and degraded 44.1 kHz mics.
 */
/**
 * @param {Float32Array} samples
 * @param {number} inputRate
 * @param {number} [outputRate]
 * @returns {Float32Array}
 */
export function resampleSpeech(samples, inputRate, outputRate = 16000) {
  if (!(samples instanceof Float32Array) || samples.length === 0) return new Float32Array();
  if (!Number.isFinite(inputRate) || inputRate <= 0 || !Number.isFinite(outputRate) || outputRate <= 0) {
    throw new RangeError("Audio sample rates must be positive");
  }
  const conditioned = highPass(samples, inputRate);
  if (inputRate === outputRate) return conditioned;

  const ratio = inputRate / outputRate;
  const outputLength = Math.max(1, Math.floor(conditioned.length / ratio));
  const output = new Float32Array(outputLength);
  const halfTaps = 8;
  const cutoff = Math.min(1, outputRate / inputRate) * 0.94;

  for (let index = 0; index < outputLength; index++) {
    const center = index * ratio;
    const first = Math.ceil(center - halfTaps);
    const last = Math.floor(center + halfTaps);
    let total = 0;
    let weight = 0;
    for (let sourceIndex = first; sourceIndex <= last; sourceIndex++) {
      if (sourceIndex < 0 || sourceIndex >= conditioned.length) continue;
      const distance = sourceIndex - center;
      const scaled = distance * cutoff;
      const sinc = Math.abs(scaled) < 1e-8
        ? 1
        : Math.sin(Math.PI * scaled) / (Math.PI * scaled);
      const window = 0.5 + 0.5 * Math.cos(Math.PI * distance / halfTaps);
      const coefficient = cutoff * sinc * window;
      total += conditioned[sourceIndex] * coefficient;
      weight += coefficient;
    }
    output[index] = weight ? Math.max(-1, Math.min(1, total / weight)) : 0;
  }
  return output;
}

/**
 * @param {Float32Array} samples
 * @param {number} inputRate
 * @param {number} [outputRate]
 * @returns {ArrayBuffer}
 */
export function floatToPcmWav(samples, inputRate, outputRate = 16000) {
  const resampled = resampleSpeech(samples, inputRate, outputRate);
  const pcm = new Int16Array(resampled.length);
  for (let index = 0; index < resampled.length; index++) {
    const value = resampled[index];
    pcm[index] = value < 0 ? value * 0x8000 : value * 0x7fff;
  }

  const wav = new ArrayBuffer(44 + pcm.byteLength);
  const view = new DataView(wav);
  /** @param {number} offset @param {string} value */
  const write = (offset, value) => {
    for (let index = 0; index < value.length; index++) view.setUint8(offset + index, value.charCodeAt(index));
  };
  write(0, "RIFF");
  view.setUint32(4, 36 + pcm.byteLength, true);
  write(8, "WAVE");
  write(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, outputRate, true);
  view.setUint32(28, outputRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  write(36, "data");
  view.setUint32(40, pcm.byteLength, true);
  new Int16Array(wav, 44).set(pcm);
  return wav;
}
