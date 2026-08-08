import assert from "node:assert/strict";
import test from "node:test";

import { inferSpeechLanguage, selectBrowserSpeechVoice } from "../src/speech_preferences.js";

const voices = [
  { name: "Daniel", lang: "en-GB", default: true },
  { name: "Anna", lang: "de-DE", default: false },
  { name: "Samantha", lang: "en-US", default: false },
];

test("system speech follows German voice input language", () => {
  assert.equal(selectBrowserSpeechVoice(voices, "de-DE")?.name, "Anna");
});

test("English keeps the JARVIS-style British voice", () => {
  assert.equal(selectBrowserSpeechVoice(voices, "en-GB")?.name, "Daniel");
});

test("an explicitly selected English voice never gives German an English accent", () => {
  assert.equal(selectBrowserSpeechVoice(voices, "de-DE", "Daniel")?.name, "Anna");
  assert.equal(selectBrowserSpeechVoice(voices, "en-GB", "Daniel")?.name, "Daniel");
});

test("a German masculine voice is preferred when the system provides one", () => {
  const bilingualVoices = [
    ...voices,
    { name: "Eddy (Deutsch (Deutschland))", lang: "de-DE", default: false },
  ];
  assert.equal(
    selectBrowserSpeechVoice(bilingualVoices, "de-DE", "Daniel")?.name,
    "Eddy (Deutsch (Deutschland))",
  );
});

test("Windows prefers matching masculine German and English voices", () => {
  const windowsVoices = [
    { name: "Microsoft Katja - German (Germany)", lang: "de-DE", default: true },
    { name: "Microsoft Stefan - German (Germany)", lang: "de-DE", default: false },
    { name: "Microsoft George - English (United Kingdom)", lang: "en-GB", default: false },
  ];
  assert.equal(selectBrowserSpeechVoice(windowsVoices, "de-DE")?.name, "Microsoft Stefan - German (Germany)");
  assert.equal(selectBrowserSpeechVoice(windowsVoices, "en-GB")?.name, "Microsoft George - English (United Kingdom)");
});

test("unknown languages fall back to the system default", () => {
  assert.equal(selectBrowserSpeechVoice(voices, "fr-FR")?.name, "Daniel");
});

test("automatic speech detects German answers locally", () => {
  assert.equal(inferSpeechLanguage("Ja, ich kann das für dich machen.", "auto"), "de-DE");
  assert.equal(inferSpeechLanguage("Öffne bitte den Kalender.", "auto"), "de-DE");
  assert.equal(inferSpeechLanguage("Gern.", "auto"), "de-DE");
  assert.equal(inferSpeechLanguage("Bereit.", "auto"), "de-DE");
});

test("automatic speech detects English answers locally", () => {
  assert.equal(inferSpeechLanguage("Yes, I can do that for you.", "auto"), "en-GB");
  assert.equal(inferSpeechLanguage("Ready.", "auto"), "en-GB");
});

test("an explicit output language always wins", () => {
  assert.equal(inferSpeechLanguage("This is English.", "de-DE"), "de-DE");
  assert.equal(inferSpeechLanguage("Das ist Deutsch.", "en-US"), "en-US");
});
