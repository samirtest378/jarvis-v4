"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const { focusExistingWindow } = require("../single_instance.cjs");

test("an existing minimized JARVIS window is restored instead of duplicated", () => {
  const calls = [];
  const window = {
    isDestroyed: () => false,
    isMinimized: () => true,
    restore: () => calls.push("restore"),
    show: () => calls.push("show"),
    focus: () => calls.push("focus"),
  };

  assert.equal(focusExistingWindow(window), true);
  assert.deepEqual(calls, ["restore", "show", "focus"]);
});

test("a missing or closed window is never treated as reusable", () => {
  assert.equal(focusExistingWindow(null), false);
  assert.equal(focusExistingWindow({ isDestroyed: () => true }), false);
});
