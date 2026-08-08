import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const source = readFileSync(join(root, "src", "settings.ts"), "utf8");

test("settings use real pages instead of one long scrolling form", () => {
  assert.match(source, /const SETTINGS_PAGES/);
  assert.match(source, /showSettingsPage\(button\.dataset\.settingsTarget/);
  assert.match(source, /section\.style\.display = visible\.has\(sectionId\)/);
  assert.match(source, /role="tablist"/);
  assert.match(source, /aria-selected="true"/);
});

test("advanced key storage stays available without cluttering the main AI page", () => {
  assert.match(source, /<summary>Security &amp; key storage<\/summary>/);
  assert.match(source, /id="desktop-storage-field"/);
});

test("settings offer a simple German and English interface choice", () => {
  const i18n = readFileSync(join(root, "src", "i18n.ts"), "utf8");
  assert.match(source, /id="input-ui-language"/);
  assert.match(source, /provider === "openai"\s*\?\s*model/);
  assert.match(i18n, /"Settings": "Einstellungen"/);
  assert.match(i18n, /jarvis_ui_language/);
});

test("Windows exposes native Outlook mail and calendar instead of hiding Mac-only rows", () => {
  assert.match(source, /data-connection="mail" data-native-office/);
  assert.match(source, /data-connection="calendar" data-native-office/);
  assert.match(source, /nativeMail: "Outlook Mail"/);
  assert.match(source, /nativeCalendar: "Outlook Calendar"/);
  assert.match(source, /renderConnectionRow\("mail", status\.mail_accessible/);
});

test("private local JARVIS notes stay visible on Windows and Linux", () => {
  const i18n = readFileSync(join(root, "src", "i18n.ts"), "utf8");
  assert.match(source, /id="status-private-notes"/);
  assert.match(source, /status\.capabilities\.private_notes/);
  assert.match(i18n, /"Private JARVIS notes": "Private JARVIS-Notizen"/);
});

test("Windows and Linux disclose the hard local recognition memory limit", () => {
  assert.match(source, /\["win32", "linux"\]\.includes/);
  assert.match(source, /local_memory_budget_mb \/ 1024/);
  assert.match(source, /Memory is hard-limited/);
});

test("permission controls use the active operating system and accept Windows screen availability", () => {
  assert.doesNotMatch(source, /setSectionFeedback\("access-feedback", "Asking macOS/);
  assert.match(source, /Checking \$\{platform\.systemName\} privacy controls/);
  assert.match(source, /accessPresentation\(status\.screen\)\.ready/);
  assert.match(source, /systemName: "Windows"/);
  assert.match(source, /systemName: "Linux"/);
});

test("permissions can be requested once and the saved setup is not prompted again", () => {
  assert.match(source, /requestAllSystemAccess\(\)/);
  assert.match(source, /dataset\.setupDone/);
  assert.match(source, /JARVIS will not ask again/);
});

test("first launch opens the one-time permission setup even when intelligence is already ready", () => {
  assert.match(source, /function enterPermissionSetupMode\(\)/);
  assert.match(source, /if \(access && !access\.setup\?\.completed\)/);
  assert.match(source, /Allow everything once/);
  assert.match(source, /isPermissionOnlySetup = false/);
});
