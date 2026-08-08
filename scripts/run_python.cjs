"use strict";

// Run repository maintenance scripts with a real Python 3.11+ interpreter on
// Windows and Unix without relying on a platform-specific `python3` alias.
const { spawnSync } = require("node:child_process");

const requested = process.argv.slice(2);
if (!requested.length) {
  console.error("Usage: node scripts/run_python.cjs <script> [arguments]");
  process.exit(2);
}

const configured = String(process.env.JARVIS_BUILD_PYTHON || "").trim();
const candidates = configured
  ? [[configured, []]]
  : process.platform === "win32"
    ? [["py", ["-3.13"]], ["py", ["-3.12"]], ["py", ["-3.11"]], ["python", []]]
    : [["python3.13", []], ["python3.12", []], ["python3.11", []], ["python3", []]];

for (const [command, prefix] of candidates) {
  const version = spawnSync(
    command,
    [...prefix, "-c", "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
    { stdio: "ignore", windowsHide: true },
  );
  if (version.error || version.status !== 0) continue;

  const result = spawnSync(command, [...prefix, ...requested], {
    stdio: "inherit",
    windowsHide: true,
  });
  if (result.error) {
    console.error(`Could not start ${command}: ${result.error.message}`);
    process.exit(2);
  }
  process.exit(result.status ?? 2);
}

console.error("JARVIS v4 needs Python 3.11 or newer.");
process.exit(2);
