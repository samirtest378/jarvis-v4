import assert from "node:assert/strict";
import test from "node:test";

import { voiceLanguageStateText, voicePackForLanguage } from "../src/voice_language.js";

test("the language switch selects the pack that can speak it", () => {
  assert.equal(voicePackForLanguage("en-GB"), "current");
  assert.equal(voicePackForLanguage("de-DE"), "current");
  assert.equal(voicePackForLanguage("auto"), "current");
  assert.equal(voicePackForLanguage("de-DE", false), "multilingual");
  assert.equal(voicePackForLanguage("en-US", false), "current");
});

test("the bilingual pack is named as speaking both languages", () => {
  const text = voiceLanguageStateText({ local_ready: true, local_languages: ["de", "en"] });
  assert.match(text, /German & English/);
});

test("the compact bilingual voice is identified as the fast Apple Silicon path", () => {
  const text = voiceLanguageStateText({
    local_ready: true,
    local_mode: "moss-nano",
    local_languages: ["de", "en"],
  });
  assert.match(text, /Fast JARVIS voice/);
  assert.match(text, /Apple Silicon/);
});

test("the smooth bilingual voice names the shared cross-platform profiles", () => {
  const text = voiceLanguageStateText({
    local_ready: true,
    local_mode: "neutts-nano",
    local_languages: ["de", "en"],
  });
  assert.match(text, /Smooth JARVIS voice/);
  assert.match(text, /V2-matched/);
  assert.match(text, /macOS, Windows, and Linux/);
});

test("the legacy bilingual voice still discloses its measured limitation", () => {
  const text = voiceLanguageStateText({
    local_ready: true,
    local_mode: "multilingual",
    local_languages: ["de", "en"],
  });
  assert.match(text, /slow to generate/);
});

test("English-only says where the German voice is", () => {
  const installed = voiceLanguageStateText({
    local_ready: true,
    local_languages: ["en"],
    bilingual_pack_installed: true,
  });
  assert.match(installed, /Choose Deutsch or Automatic/);

  const missing = voiceLanguageStateText({
    local_ready: true,
    local_languages: ["en"],
    bilingual_pack_installed: false,
  });
  assert.match(missing, /not installed on this computer/);
});

test("no pack at all does not claim a cloned voice is speaking", () => {
  assert.match(voiceLanguageStateText({ local_ready: false }), /not installed/);
  assert.match(voiceLanguageStateText(undefined), /not installed/);
});
