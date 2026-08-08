"use strict";

const { execFileSync } = require("node:child_process");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const SPEECH_MODEL_NAME = "ggml-large-v3-turbo-q8_0.bin";
const SPEECH_MODEL_SHA256 = "317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1";
const SPEECH_RUNTIME_VERSION = "1.8.6";
const SHARED_VOICE_HASHES = Object.freeze({
  "profile-en.npy": "276f750c643f95b2b6c6a0c82e90c9e6d0578661ab6fee240f8a128bbd57c75d",
  "profile-de.npy": "279ff6c17daa00db4cffe872a7a8a9c70814782077f0514c51c6851469d1b22a",
  "profiles.json": "b9a9cdbeb126920ec26dcf7b476e43d27b46871ec1cb8cccd1a4deb8d38dacfe",
  "models/neutts-nano-german-Q4_0.gguf": "c0a2e494d581afdac8f647f5b3c8644d6a0d793152d2f0387c860b92fcc1dd2b",
  "models/neutts-nano-Q4_0.gguf": "85466ca06aeb487e5e8d0263367166e125969e3f4b07245db009aee223702c86",
  "models/neucodec-int8.onnx": "3ddd9e56396e6029e0e948ac0255c89c803f981f23dcf4c154f50820bd74a6b3",
});

/**
 * Keep unpacked development bundles out of Spotlight and LaunchServices-based
 * app pickers. The DMG/ZIP artifacts remain indexable and are the supported
 * installation path; only the temporary appOutDir is excluded.
 */
function markBuildOutputNonIndexable(context) {
  fs.mkdirSync(context.appOutDir, { recursive: true });
  fs.closeSync(fs.openSync(path.join(context.appOutDir, ".metadata_never_index"), "a"));
}

function sha256(target) {
  const digest = crypto.createHash("sha256");
  digest.update(fs.readFileSync(target));
  return digest.digest("hex");
}

function newestMtime(target) {
  const stat = fs.statSync(target);
  if (!stat.isDirectory()) return stat.mtimeMs;
  return fs.readdirSync(target, { withFileTypes: true }).reduce((newest, entry) => {
    const child = path.join(target, entry.name);
    return Math.max(newest, newestMtime(child));
  }, stat.mtimeMs);
}

/**
 * Refuse to publish a shell around an older frozen backend. This catches an
 * easy-to-miss release mistake: running electron-builder directly after a
 * Python/provider edit instead of using the complete npm build pipeline.
 */
function assertBackendIsFresh(context) {
  const projectRoot = path.resolve(__dirname, "..", "..");
  const executable = context.electronPlatformName === "win32" ? "jarvis-server.exe" : "jarvis-server";
  const distBackend = path.join(projectRoot, "desktop", "dist-backend");
  const candidates = [
    path.join(distBackend, "jarvis-server", executable),
    path.join(distBackend, executable),
  ];
  const backend = candidates.find(fs.existsSync);
  if (!backend) {
    throw new Error(`Packaged backend source is missing: ${candidates[0]}. Run npm run build.`);
  }

  const inputs = fs.readdirSync(projectRoot, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".py"))
    .map((entry) => path.join(projectRoot, entry.name));
  inputs.push(
    path.join(projectRoot, ".env.example"),
    path.join(projectRoot, "requirements.txt"),
    path.join(projectRoot, "requirements-build.lock.txt"),
    path.join(projectRoot, "scripts", "build_backend.py"),
    path.join(projectRoot, "frontend", "dist"),
  );

  const newestInput = Math.max(...inputs.filter(fs.existsSync).map(newestMtime));
  if (fs.statSync(backend).mtimeMs + 1000 < newestInput) {
    throw new Error(
      "Refusing to package a stale Python backend. Run the complete `npm run build` command so current provider and UI code are embedded.",
    );
  }
}

/** Refuse to ship without the pinned, local speech engine and model. */
function assertSpeechRuntime(context) {
  const resources = context.electronPlatformName === "darwin"
    ? path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents", "Resources")
    : path.join(context.appOutDir, "resources");
  const runtime = path.join(resources, "speech-runtime");
  const executable = path.join(runtime, context.electronPlatformName === "win32" ? "whisper-server.exe" : "whisper-server");
  const model = path.join(runtime, SPEECH_MODEL_NAME);
  const license = path.join(runtime, "WHISPER_CPP_LICENSE.txt");
  const metadata = path.join(runtime, "RUNTIME.txt");
  for (const required of [executable, model, license, metadata]) {
    if (!fs.existsSync(required) || fs.statSync(required).size === 0) {
      throw new Error(`Packaged offline speech component is missing or empty: ${required}`);
    }
  }
  const runtimeText = fs.readFileSync(metadata, "utf8");
  if (!runtimeText.includes(`whisper.cpp v${SPEECH_RUNTIME_VERSION}`) || !runtimeText.includes(SPEECH_MODEL_SHA256)) {
    throw new Error("Packaged offline speech metadata does not match the pinned release.");
  }
  if (sha256(model) !== SPEECH_MODEL_SHA256) {
    throw new Error("Packaged offline speech model failed its SHA-256 integrity check.");
  }
  if (!/MIT License|Permission is hereby granted/i.test(fs.readFileSync(license, "utf8"))) {
    throw new Error("Packaged whisper.cpp license notice is invalid.");
  }
}

/** Ensure every installer receives the same verified English and German voice. */
function assertBundledVoice(context) {
  const root = context.electronPlatformName === "darwin"
    ? path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, "Contents", "Resources", "voice-pack")
    : path.join(context.appOutDir, "resources", "voice-pack");
  const manifestPath = path.join(root, "voice-pack.json");
  if (!fs.existsSync(manifestPath)) throw new Error("The native JARVIS voice pack is missing from the installer.");
  const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
  if (
    manifest.engine_mode !== "neutts-nano"
    || manifest.platform !== context.electronPlatformName
    || manifest.arch !== process.arch
    || manifest.mastering !== "reference-video-crisp-v1"
    || !Array.isArray(manifest.languages)
    || !manifest.languages.includes("de")
    || !manifest.languages.includes("en")
  ) {
    throw new Error("The bundled voice manifest does not match the bilingual NeuTTS release.");
  }
  for (const [relative, expected] of Object.entries(SHARED_VOICE_HASHES)) {
    const target = path.join(root, ...relative.split("/"));
    if (!fs.existsSync(target) || sha256(target) !== expected) {
      throw new Error(`Bundled voice identity differs across platforms: ${relative}`);
    }
  }
}

/**
 * Electron's downloaded framework carries signatures that become invalid when
 * an unsigned local build is repackaged. Apply a complete ad-hoc signature so
 * macOS can verify the bundle and keep privacy permissions tied to one app ID.
 * A configured Developer ID signature is still applied by electron-builder
 * afterwards for release builds.
 */
module.exports = async function afterPack(context) {
  markBuildOutputNonIndexable(context);
  assertBackendIsFresh(context);
  assertSpeechRuntime(context);
  assertBundledVoice(context);
  if (context.electronPlatformName !== "darwin") return;
  const appPath = path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`);
  const infoPlist = path.join(appPath, "Contents", "Info.plist");
  const entitlements = path.join(context.packager.projectDir, "build", "entitlements.mac.plist");
  const inheritedEntitlements = path.join(context.packager.projectDir, "build", "entitlements.mac.inherit.plist");
  // The directory build nests the executable one level deeper. The flat path
  // remains valid for an older one-file backend.
  const backendRoot = path.join(appPath, "Contents", "Resources", "backend");
  const nestedBackend = path.join(backendRoot, "jarvis-server", "jarvis-server");
  const backend = fs.existsSync(nestedBackend) ? nestedBackend : path.join(backendRoot, "jarvis-server");
  // Electron's base plist permits arbitrary network loads for generic apps.
  // JARVIS v4's renderer needs only its authenticated localhost backend.
  execFileSync(
    "/usr/libexec/PlistBuddy",
    ["-c", "Set :NSAppTransportSecurity:NSAllowsArbitraryLoads false", infoPlist],
    { stdio: "inherit" },
  );
  execFileSync(
    "/usr/bin/codesign",
    [
      "--force",
      "--sign", "-",
      "--timestamp=none",
      "--options", "runtime",
      "--entitlements", inheritedEntitlements,
      backend,
    ],
    { stdio: "inherit" },
  );
  execFileSync(
    "/usr/bin/codesign",
    [
      "--force",
      "--deep",
      "--sign", "-",
      "--timestamp=none",
      "--options", "runtime",
      "--entitlements", entitlements,
      "--identifier", "ai.jarvis.v4",
      appPath,
    ],
    { stdio: "inherit" },
  );
};

module.exports.assertBackendIsFresh = assertBackendIsFresh;
module.exports.assertSpeechRuntime = assertSpeechRuntime;
module.exports.assertBundledVoice = assertBundledVoice;
module.exports.markBuildOutputNonIndexable = markBuildOutputNonIndexable;
