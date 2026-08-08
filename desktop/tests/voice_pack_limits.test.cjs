"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");
const {
  VOICE_PACK_MAX_FILES,
  VOICE_PACK_MAX_BYTES,
  withinVoicePackLimits,
} = require("../voice_pack_limits.cjs");

test("the real 6,325-file voice pack fits the bounded installer", () => {
  assert.equal(withinVoicePackLimits(6_325, 3_984_502_929), true);
});

test("oversized or pathologically fragmented packs remain blocked", () => {
  assert.equal(withinVoicePackLimits(VOICE_PACK_MAX_FILES + 1, 1), false);
  assert.equal(withinVoicePackLimits(1, VOICE_PACK_MAX_BYTES + 1), false);
  assert.equal(withinVoicePackLimits(-1, 1), false);
});
