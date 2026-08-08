"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const script = path.resolve(__dirname, "..", "..", "scripts", "prepare_speech_runtime.py");
const candidates = process.platform === "win32"
  ? [["py", ["-3"]], ["python", []]]
  : [["python3", []], ["python", []]];

for (const [command, prefix] of candidates) {
  const result = spawnSync(command, [...prefix, script], {
    cwd: path.resolve(__dirname, ".."),
    env: process.env,
    stdio: "inherit",
    windowsHide: true,
  });
  if (!result.error) process.exit(result.status ?? 2);
}

console.error("Python 3 is required to prepare offline speech recognition.");
process.exit(2);
