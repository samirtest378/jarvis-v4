import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const mainSource = fs.readFileSync(path.resolve(testDir, "../src/main.ts"), "utf8");
const settingsSource = fs.readFileSync(path.resolve(testDir, "../src/settings.ts"), "utf8");

test("wake-on-startup follows the persistent backend setting across random ports", () => {
  assert.match(mainSource, /status\.tts\.wake_enabled === true/);
  assert.match(mainSource, /persistedSettingsReady\.then/);
  assert.match(mainSource, /\/api\/settings\/wake/);
  assert.match(settingsSource, /wake_enabled: wakeEnabled/);
  assert.match(settingsSource, /status\.tts\.wake_enabled \? "on" : "off"/);
});
