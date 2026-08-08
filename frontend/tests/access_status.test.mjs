import assert from "node:assert/strict";
import test from "node:test";

import { accessPresentation, summarizeCoreAccess } from "../src/access_status.js";

test("permission states use clear customer-facing labels", () => {
  assert.deepEqual(accessPresentation("granted"), { tone: "green", label: "Allowed", ready: true });
  assert.deepEqual(accessPresentation("denied"), { tone: "red", label: "Blocked", ready: false });
  assert.deepEqual(accessPresentation("not-determined"), { tone: "yellow", label: "Not requested", ready: false });
});

test("Windows-managed microphone is not falsely reported as granted", () => {
  const result = summarizeCoreAccess("win32", {
    microphone: "managed",
    screen: "available",
    files: "granted",
    automation: { calendar: "unavailable", mail: "unavailable", notes: "unavailable" },
  });
  assert.equal(result.ready, 2);
  assert.equal(result.attention, 1);
  assert.match(result.message, /1 need attention/);
});

test("macOS all-clear requires every core automation probe", () => {
  const status = {
    microphone: "granted",
    screen: "granted",
    files: "granted",
    automation: { calendar: "granted", mail: "granted", notes: "unknown" },
  };
  assert.equal(summarizeCoreAccess("darwin", status).attention, 1);
  status.automation.notes = "granted";
  assert.equal(summarizeCoreAccess("darwin", status).attention, 0);
});
