"use strict";

const platform = String(process.env.JARVIS_RELEASE_PLATFORM || "").toLowerCase();

function requireVariables(names, label) {
  const missing = names.filter((name) => !String(process.env[name] || "").trim());
  if (missing.length) {
    console.error(`${label} is missing required secret(s): ${missing.join(", ")}`);
    process.exit(2);
  }
}

if (platform === "macos") {
  requireVariables(["CSC_LINK", "CSC_KEY_PASSWORD"], "macOS signing");
  const apiKeyAuth = ["APPLE_API_KEY", "APPLE_API_KEY_ID", "APPLE_API_ISSUER"]
    .every((name) => String(process.env[name] || "").trim());
  const appleIdAuth = ["APPLE_ID", "APPLE_APP_SPECIFIC_PASSWORD", "APPLE_TEAM_ID"]
    .every((name) => String(process.env[name] || "").trim());
  if (!apiKeyAuth && !appleIdAuth) {
    console.error(
      "macOS notarization needs either APPLE_API_KEY + APPLE_API_KEY_ID + APPLE_API_ISSUER or APPLE_ID + APPLE_APP_SPECIFIC_PASSWORD + APPLE_TEAM_ID.",
    );
    process.exit(2);
  }
} else if (platform === "windows") {
  requireVariables(["WIN_CSC_LINK", "WIN_CSC_KEY_PASSWORD"], "Windows signing");
} else if (platform === "linux") {
  // AppImage and Debian packages do not use Electron's Apple/AuthentiCode
  // certificate flow. Release integrity is provided by the generated SHA-256
  // file; repository/package signing can be added by the distributor.
} else {
  console.error("JARVIS_RELEASE_PLATFORM must be macos, windows, or linux.");
  process.exit(2);
}

console.log(`${platform} release signing inputs are present.`);
