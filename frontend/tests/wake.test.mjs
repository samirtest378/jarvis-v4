import assert from "node:assert/strict";
import test from "node:test";

import { isWakeFragment, parseWakeCommand } from "../src/wake.js";

test("accepts natural punctuation and extracts a German command", () => {
  assert.deepEqual(parseWakeCommand("Hey, Jarvis. Öffne YouTube."), {
    matched: true,
    command: "Öffne YouTube.",
  });
  assert.deepEqual(parseWakeCommand("Hey Jarvis, open YouTube."), {
    matched: true,
    command: "open YouTube.",
  });
  assert.deepEqual(parseWakeCommand("Hey JARVIS, prüfe meine E-Mails."), {
    matched: true,
    command: "prüfe meine E-Mails.",
  });
});

test("accepts constrained phonetic spellings produced by local STT", () => {
  assert.deepEqual(parseWakeCommand("Helgravis. Antworte kurz."), {
    matched: true,
    command: "Antworte kurz.",
  });
  assert.deepEqual(parseWakeCommand("Helgrabis, öffne YouTube."), {
    matched: true,
    command: "öffne YouTube.",
  });
  assert.deepEqual(parseWakeCommand("Helbrabis, wie geht es dir heute?"), {
    matched: true,
    command: "wie geht es dir heute?",
  });
  assert.deepEqual(parseWakeCommand("Her Gravis, auf YouTube."), {
    matched: true,
    command: "auf YouTube.",
  });
  assert.equal(parseWakeCommand("Okay, Javis!").matched, true);
  assert.equal(parseWakeCommand("Hello Jervis, open Calendar.").matched, true);
  assert.equal(parseWakeCommand("Hey Tscharvis, öffne Kalender.").matched, true);
});

test("does not wake for a normal mention or unrelated speech", () => {
  assert.equal(parseWakeCommand("Ich habe gestern über Jarvis gesprochen.").matched, false);
  assert.equal(parseWakeCommand("YouTube. Gmail.").matched, false);
  assert.equal(parseWakeCommand("hey").matched, false);
});

test("recognizes overlap-only fragments without treating them as commands", () => {
  assert.equal(isWakeFragment("Hey."), true);
  assert.equal(isWakeFragment("Jarvis!"), true);
  assert.equal(isWakeFragment("Jervis."), true);
  assert.equal(isWakeFragment("öffne YouTube"), false);
});
