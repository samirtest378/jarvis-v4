import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const mainSource = fs.readFileSync(path.resolve(testDir, "../src/main.ts"), "utf8");
const settingsSource = fs.readFileSync(path.resolve(testDir, "../src/settings.ts"), "utf8");
const serverSource = fs.readFileSync(path.resolve(testDir, "../../server.py"), "utf8");
const exampleEnvironment = fs.readFileSync(path.resolve(testDir, "../../.env.example"), "utf8");

test("wake-on-startup follows the persistent backend setting across random ports", () => {
  assert.match(mainSource, /status\.tts\.wake_enabled === true/);
  assert.match(mainSource, /persistedSettingsReady\.then/);
  assert.match(mainSource, /\/api\/settings\/wake/);
  assert.match(settingsSource, /wake_enabled: wakeEnabled/);
  assert.match(settingsSource, /status\.tts\.wake_enabled \? "on" : "off"/);
});

test("fresh Windows installs start Hey JARVIS only after the permission step", () => {
  assert.match(serverSource, /JARVIS_WAKE_ENABLED", "1"/);
  assert.match(exampleEnvironment, /^JARVIS_WAKE_ENABLED=1$/m);
  assert.match(settingsSource, /value="on">On — answer whenever you say “Hey JARVIS” \(recommended\)/);
  assert.match(settingsSource, /if \(permissionOnlyCompleted\)[\s\S]*jarvis:wake-setting/);
  assert.match(settingsSource, /The Windows voice is CPU-only/);
});
