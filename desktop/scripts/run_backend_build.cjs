"use strict";

const { spawnSync } = require("node:child_process");
const path = require("node:path");

const buildScript = path.resolve(__dirname, "..", "..", "scripts", "build_backend.py");
const configured = String(process.env.JARVIS_BUILD_PYTHON || "").trim();
const candidates = configured
  ? [[configured, []]]
  : process.platform === "win32"
    ? [["py", ["-3.13"]], ["py", ["-3.12"]], ["py", ["-3.11"]], ["python", []]]
    : [["python3.13", []], ["python3.12", []], ["python3.11", []], ["python3", []], ["python", []]];

function supportsJarvis(command, prefix) {
  const check = spawnSync(
    command,
    [
      ...prefix,
      "-c",
      "import sys, PyInstaller; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)",
    ],
    { stdio: "ignore", windowsHide: true },
  );
  return !check.error && check.status === 0;
}

const selected = candidates.find(([command, prefix]) => supportsJarvis(command, prefix));
if (!selected) {
  console.error(
    "JARVIS v4 needs Python 3.11 or newer with the verified build requirements. Install requirements-build.lock.txt, or set JARVIS_BUILD_PYTHON to that Python executable.",
  );
  process.exit(2);
}

const [command, prefix] = selected;
const result = spawnSync(command, [...prefix, buildScript], {
  cwd: path.resolve(__dirname, ".."),
  env: process.env,
  stdio: "inherit",
  windowsHide: true,
});

if (result.error) {
  console.error(`Could not start ${command}: ${result.error.message}`);
  process.exit(2);
}
process.exit(result.status ?? 2);
