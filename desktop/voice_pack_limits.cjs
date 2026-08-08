"use strict";

const VOICE_PACK_MAX_FILES = 10_000;
const VOICE_PACK_MAX_BYTES = 8 * 1024 ** 3;

function withinVoicePackLimits(files, bytes) {
  return Number.isSafeInteger(files)
    && Number.isSafeInteger(bytes)
    && files >= 0
    && bytes >= 0
    && files <= VOICE_PACK_MAX_FILES
    && bytes <= VOICE_PACK_MAX_BYTES;
}

module.exports = Object.freeze({
  VOICE_PACK_MAX_FILES,
  VOICE_PACK_MAX_BYTES,
  withinVoicePackLimits,
});
