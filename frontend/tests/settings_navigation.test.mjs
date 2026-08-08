import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const source = readFileSync(join(root, "src", "settings.ts"), "utf8");
const style = readFileSync(join(root, "src", "style.css"), "utf8");
const voiceSource = readFileSync(join(root, "src", "voice.ts"), "utf8");

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

test("recognition stays on the configured bilingual backend and refreshes after settings", () => {
  assert.doesNotMatch(voiceSource, /webkitSpeechRecognition|createSystemSpeechInput/);
  assert.match(voiceSource, /refresh\(\) \{/);
  assert.match(voiceSource, /selected\?\.stop\(\)/);
  assert.match(voiceSource, /Choose Local recognition in Voice settings/);
});

test("permission controls use the active operating system and accept Windows screen availability", () => {
  assert.doesNotMatch(source, /setSectionFeedback\("access-feedback", "Asking macOS/);
  assert.match(source, /Checking \$\{platform\.systemName\} privacy controls/);
  assert.match(source, /accessPresentation\(status\.screen\)\.ready/);
  assert.match(source, /systemName: "Windows"/);
  assert.match(source, /systemName: "Linux"/);
  assert.doesNotMatch(source, /unless macOS revokes access/);
  assert.doesNotMatch(source, /Approve each macOS sheet/);
  assert.match(source, /platform\.permissionPrompt/);
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

test("Windows caption buttons never cover JARVIS microphone or settings controls", () => {
  assert.match(style, /html\[data-platform="win32"\] #controls \{ top: 2px; right: 150px; \}/);
  assert.match(style, /html\[data-platform="win32"\] #menu-dropdown \{ top: 48px; right: 150px; \}/);
  assert.match(style, /html\[data-platform="win32"\] \.settings-panel[\s\S]*top: 44px/);
});

test("Google services use branded icons and start consent from the whole row", () => {
  assert.match(source, /const GMAIL_ICON = `<svg/);
  assert.match(source, /const GOOGLE_CALENDAR_ICON = `<svg/);
  assert.equal((source.match(/data-google-connect role="button"/g) || []).length, 2);
  assert.match(source, /const startGoogleConnection = async/);
  assert.match(source, /desktop\.connectGoogle\(\{ clientId, clientSecret/);
  assert.match(source, /event\.key !== "Enter" && event\.key !== " "/);
  assert.match(source, /showSettingsPage\("section-access"\)/);
  assert.match(source, /setup\.open = true/);
  assert.doesNotMatch(source, /<summary>Connect Google directly/);
});

test("settings use simple icon tabs and recognizable service icons", () => {
  assert.equal((source.match(/class="settings-nav-icon"/g) || []).length, 6);
  assert.match(style, /\.settings-nav\s*\{[\s\S]*grid-template-columns: repeat\(6, minmax\(0, 1fr\)\)/);
  for (const icon of ["OUTLOOK", "WINDOWS_CALENDAR", "FOLDER", "MICROPHONE", "SPOTIFY"]) {
    assert.match(source, new RegExp("const " + icon + "_ICON = `<svg"));
  }
  for (const logo of ["outlook", "calendar", "files", "mic", "spotify", "gmail", "gcal"]) {
    assert.match(source, new RegExp(`data-logo="${logo}"`));
  }
  assert.match(style, /\.connection-logo-brand svg/);
});

test("the initial OpenAI selection shows the matching key field", () => {
  assert.match(source, /data-provider-key="openai">\s*<label>OpenAI API Key/);
  assert.match(source, /data-provider-key="anthropic" hidden>\s*<label>Anthropic API Key/);
});

test("Windows intelligence stays cloud-only and defaults to GPT-5.4 Nano", () => {
  assert.match(source, /<option value="openai">OpenAI \/ ChatGPT API<\/option>/);
  assert.match(source, /model: "gpt-5\.4-nano"/);
  assert.doesNotMatch(source, /value="ollama"|Local AI · Ollama|btn-install-local-model/);
});

test("ticket dashboard is visibly read-only and keeps summaries local", () => {
  assert.match(source, /data-settings-target="section-tickets"/);
  assert.match(source, /\/api\/ticket-dashboard\/analyze/);
  assert.match(source, /snapshot: pastedText/);
  assert.match(source, /if \(snapshot\) snapshot\.value = ""/);
  assert.match(source, /element\.textContent = result\.metrics\[metric\]/);
  assert.match(source, /nothing sent to the AI provider/);
  assert.doesNotMatch(source, /allow_ai_summary/);
  const renderer = source.match(/function renderTicketDashboard[\s\S]*?\n}/)?.[0] || "";
  assert.doesNotMatch(renderer, /innerHTML/);
  assert.match(style, /\.ticket-metrics/);
});
