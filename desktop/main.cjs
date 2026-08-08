const { app, BrowserWindow, desktopCapturer, dialog, ipcMain, Menu, nativeTheme, safeStorage, session, shell, systemPreferences } = require("electron");
const { spawn } = require("node:child_process");
const crypto = require("node:crypto");
const extractZip = require("extract-zip");
const fs = require("node:fs");
const http = require("node:http");
const net = require("node:net");
const path = require("node:path");
const {
  VOICE_PACK_MAX_FILES,
  VOICE_PACK_MAX_BYTES,
  withinVoicePackLimits,
} = require("./voice_pack_limits.cjs");
const {
  SECRET_DEFINITIONS,
  buildBackendSecretTransfer,
  meaningfulSecret,
  normalizeStorageMode,
  resolveSecretsForMode,
} = require("./secret_config.cjs");
const { buildDiagnostics } = require("./diagnostics.cjs");
const { focusExistingWindow } = require("./single_instance.cjs");
const {
  buildAuthorizationUrl,
  createPkce,
  exchangeAuthorizationCode,
  revokeToken,
  validateClientId,
} = require("./google_oauth.cjs");

const PROJECT_ROOT = path.resolve(__dirname, "..");

// Use one stable Windows identity for the executable, shortcuts, taskbar and
// notifications so a second launch focuses JARVIS instead of looking like a
// separate application.
app.setName("JARVIS v4");
if (process.platform === "win32") app.setAppUserModelId("ai.jarvis.v4");

function normalizeLocalDevelopmentUrl(value) {
  const raw = String(value || "").trim();
  if (!raw) return "";
  const parsed = new URL(raw);
  if (
    !["http:", "https:"].includes(parsed.protocol)
    || !["127.0.0.1", "localhost", "::1"].includes(parsed.hostname)
    || parsed.username
    || parsed.password
  ) {
    throw new Error("JARVIS_DEV_SERVER_URL must be a credential-free loopback URL.");
  }
  return parsed.toString();
}

const DEV_URL = normalizeLocalDevelopmentUrl(process.env.JARVIS_DEV_SERVER_URL);
const isDevelopment = Boolean(DEV_URL);

let mainWindow = null;
let backendProcess = null;
let backendPort = 0;
let googleOAuthInProgress = false;
const authToken = crypto.randomBytes(32).toString("base64url");

function secretFilePath() {
  return path.join(app.getPath("userData"), "secrets.json");
}

function localSecretFilePath() {
  return path.join(app.getPath("userData"), "secrets.local.json");
}

function storagePreferencePath() {
  return path.join(app.getPath("userData"), "key-storage.json");
}

function permissionSetupPath() {
  return path.join(app.getPath("userData"), "permissions-setup.json");
}

function permissionSetupRecord() {
  const record = readJsonObject(permissionSetupPath());
  return {
    completed: record.completed === true,
    requestedAt: typeof record.requestedAt === "string" ? record.requestedAt : "",
  };
}

function readJsonObject(target) {
  try {
    const parsed = JSON.parse(fs.readFileSync(target, "utf8"));
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function writePrivateJson(target, value) {
  const temporary = `${target}.tmp`;
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  fs.writeFileSync(temporary, `${JSON.stringify(value, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(temporary, target);
  try { fs.chmodSync(target, 0o600); } catch { /* Windows user-profile ACLs apply. */ }
}

function currentStorageMode() {
  return normalizeStorageMode(readJsonObject(storagePreferencePath()).mode);
}

function writeStorageMode(mode) {
  writePrivateJson(storagePreferencePath(), { mode: normalizeStorageMode(mode) });
}

function selectedStorageBackend() {
  return typeof safeStorage.getSelectedStorageBackend === "function"
    ? safeStorage.getSelectedStorageBackend()
    : process.platform === "darwin" ? "keychain" : "os-crypt";
}

function secureStorageAvailable() {
  return safeStorage.isEncryptionAvailable() && selectedStorageBackend() !== "basic_text";
}

function readSecretStore() {
  return readJsonObject(secretFilePath());
}

function readLocalSecretStore() {
  return readJsonObject(localSecretFilePath());
}

function decryptSecret(encoded) {
  if (!encoded || !secureStorageAvailable()) return "";
  try {
    return safeStorage.decryptString(Buffer.from(encoded, "base64"));
  } catch {
    return "";
  }
}

function writeSecretStore(store) {
  writePrivateJson(secretFilePath(), store);
}

function writeLocalSecretStore(store) {
  writePrivateJson(localSecretFilePath(), store);
}

function storeSecretValue(store, key, value, mode) {
  store[key] = mode === "local" ? value : safeStorage.encryptString(value).toString("base64");
}

function resolvedSecrets() {
  const mode = currentStorageMode();
  return resolveSecretsForMode({
    mode,
    environment: process.env,
    encryptedStore: mode === "keychain" ? readSecretStore() : {},
    localStore: mode === "local" ? readLocalSecretStore() : {},
    decrypt: decryptSecret,
  });
}

function hasStoredSecrets(store) {
  return SECRET_DEFINITIONS.some((definition) => (
    typeof store?.[definition.store] === "string" && store[definition.store].trim().length > 0
  ));
}

function secretStorageStatus() {
  const mode = currentStorageMode();
  return {
    mode,
    requiresPassword: mode === "keychain" && process.platform === "darwin",
    storageBackend: mode === "local" ? "private-local-file" : selectedStorageBackend(),
    secureStorageAvailable: mode === "local" || secureStorageAvailable(),
    hasLocalSecrets: hasStoredSecrets(readLocalSecretStore()),
    hasKeychainSecrets: hasStoredSecrets(readSecretStore()),
  };
}

async function activateStoredSecretMode(requestedMode) {
  const mode = normalizeStorageMode(requestedMode);
  if (mode === "keychain" && !secureStorageAvailable()) {
    return { success: false, error: "Secure operating-system storage is unavailable." };
  }
  const store = mode === "local" ? readLocalSecretStore() : readSecretStore();
  if (!hasStoredSecrets(store)) {
    return { success: false, error: "No saved API key exists in that storage location." };
  }
  writeStorageMode(mode);
  await restartBackend();
  return {
    success: true,
    storageMode: mode,
    storageBackend: mode === "local" ? "private-local-file" : selectedStorageBackend(),
  };
}

function findAvailablePort() {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.unref();
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      const address = server.address();
      const port = typeof address === "object" && address ? address.port : 0;
      server.close(() => resolve(port));
    });
  });
}

function backendCommand() {
  if (app.isPackaged) {
    const executable = process.platform === "win32" ? "jarvis-server.exe" : "jarvis-server";
    // PyInstaller's directory build nests the executable inside a folder of
    // the same name; the flat path is kept as a fallback so an older one-file
    // backend still launches.
    const nested = path.join(process.resourcesPath, "backend", "jarvis-server", executable);
    const flat = path.join(process.resourcesPath, "backend", executable);
    const command = fs.existsSync(nested) ? nested : flat;
    return {
      command,
      args: [],
      cwd: path.dirname(command),
    };
  }

  const venvPython = process.platform === "win32"
    ? path.join(PROJECT_ROOT, ".venv", "Scripts", "python.exe")
    : path.join(PROJECT_ROOT, ".venv", "bin", "python3");
  const command = process.env.JARVIS_PYTHON
    || (fs.existsSync(venvPython) ? venvPython : process.platform === "win32" ? "python" : "python3");
  return { command, args: [path.join(PROJECT_ROOT, "server.py")], cwd: PROJECT_ROOT };
}

function waitForBackend(port, timeoutMs = 30000) {
  const startedAt = Date.now();
  return new Promise((resolve, reject) => {
    const poll = () => {
      const request = http.get(`http://127.0.0.1:${port}/api/health`, (response) => {
        response.resume();
        if (response.statusCode === 200) return resolve();
        setTimeout(poll, 200);
      });
      request.setTimeout(1000, () => request.destroy());
      request.on("error", () => {
        if (Date.now() - startedAt >= timeoutMs) {
          reject(new Error("The local assistant service did not become ready."));
        } else {
          setTimeout(poll, 200);
        }
      });
    };
    poll();
  });
}

async function startBackend() {
  if (!backendPort) backendPort = await findAvailablePort();
  const launch = backendCommand();
  const secrets = resolvedSecrets();
  const { childEnvironment, runtimeSecrets } = buildBackendSecretTransfer(
    process.env,
    secrets,
    { JARVIS_AUTH_TOKEN: authToken },
  );
  const userData = app.getPath("userData");
  const env = {
    ...childEnvironment,
    JARVIS_PORT: String(backendPort),
    JARVIS_CONFIG_DIR: path.join(userData, "config"),
    JARVIS_DATA_DIR: path.join(userData, "data"),
    JARVIS_SPEECH_RUNTIME: app.isPackaged
      ? path.join(process.resourcesPath, "speech-runtime")
      : path.join(PROJECT_ROOT, "desktop", "speech-runtime"),
    PYTHONUNBUFFERED: "1",
  };
  const activeVoicePack = activeVoicePackDirectory();
  if (activeVoicePack) env.JARVIS_LOCAL_VOICE_PACK = activeVoicePack;
  if (isDevelopment) env.JARVIS_DEV_ORIGIN = new URL(DEV_URL).origin;

  backendProcess = spawn(
    launch.command,
    [...launch.args, "--host", "127.0.0.1", "--port", String(backendPort)],
    { cwd: launch.cwd, env, stdio: ["pipe", "pipe", "pipe"], windowsHide: true },
  );
  // Deliver decrypted credentials once, then close the pipe. They never enter
  // the backend process environment or command line.
  backendProcess.stdin.on("error", () => { /* Backend startup reports the useful failure. */ });
  backendProcess.stdin.end(`${JSON.stringify(runtimeSecrets)}\n`);
  backendProcess.stdout.on("data", (chunk) => console.log(`[backend] ${chunk.toString().trimEnd()}`));
  backendProcess.stderr.on("data", (chunk) => console.error(`[backend] ${chunk.toString().trimEnd()}`));
  backendProcess.once("exit", (code, signal) => {
    console.log(`[backend] exited (${code ?? signal})`);
    backendProcess = null;
  });
  backendProcess.once("error", (error) => console.error("[backend] launch failed", error));
  await waitForBackend(backendPort);
}

function stopBackend() {
  return new Promise((resolve) => {
    if (!backendProcess) return resolve();
    const processToStop = backendProcess;
    const timer = setTimeout(() => {
      if (processToStop.exitCode === null) processToStop.kill("SIGKILL");
    }, 3000);
    processToStop.once("exit", () => {
      clearTimeout(timer);
      resolve();
    });
    processToStop.kill();
  });
}

async function restartBackend() {
  await stopBackend();
  await startBackend();
}

async function deleteAllLocalData() {
  const choice = await dialog.showMessageBox(mainWindow, {
    type: "warning",
    title: "Delete all local JARVIS data?",
    message: "This permanently removes JARVIS v4 data from this computer.",
    detail: "Saved API keys, conversations, memory, tasks, preferences, usage records, and the installed offline voice pack will be deleted. Cloud providers may retain data under their own policies.",
    buttons: ["Cancel", "Delete data & restart"],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  });
  if (choice.response !== 1) return { success: false, canceled: true };

  await stopBackend();
  const userData = app.getPath("userData");
  const targets = [
    secretFilePath(),
    localSecretFilePath(),
    storagePreferencePath(),
    permissionSetupPath(),
    path.join(userData, "config"),
    path.join(userData, "data"),
    path.join(userData, "voice-pack"),
  ];
  for (const target of targets) fs.rmSync(target, { recursive: true, force: true });
  await session.defaultSession.clearStorageData();
  app.relaunch();
  app.exit(0);
  return { success: true };
}

function runtimeConfig() {
  return {
    apiBase: `http://127.0.0.1:${backendPort}`,
    authToken,
    desktop: true,
    development: isDevelopment,
    platform: process.platform,
    arch: process.arch,
    appVersion: app.getVersion(),
  };
}

function getBackendStatus() {
  return new Promise((resolve) => {
    if (!backendPort) return resolve({ healthy: false });
    const request = http.get({
      hostname: "127.0.0.1",
      port: backendPort,
      path: "/api/settings/status",
      headers: { Authorization: `Bearer ${authToken}` },
      timeout: 2500,
    }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk) => {
        if (body.length < 1024 * 1024) body += chunk;
      });
      response.on("end", () => {
        if (response.statusCode !== 200) return resolve({ healthy: false });
        try {
          resolve({ ...JSON.parse(body), healthy: true });
        } catch {
          resolve({ healthy: false });
        }
      });
    });
    request.on("timeout", () => request.destroy());
    request.on("error", () => resolve({ healthy: false }));
  });
}

async function createDiagnostics() {
  const [backend, access] = await Promise.all([
    getBackendStatus(),
    systemAccessStatus(false),
  ]);
  return buildDiagnostics({
    appInfo: { version: app.getVersion(), packaged: app.isPackaged },
    runtime: {
      platform: process.platform,
      arch: process.arch,
      osVersion: typeof process.getSystemVersion === "function" ? process.getSystemVersion() : process.version,
      backendRunning: Boolean(backendProcess),
    },
    backend,
    storage: secretStorageStatus(),
    access,
    voicePack: voicePackStatus(activeVoicePackDirectory() || voicePackDirectory()),
  });
}

async function exportDiagnostics() {
  const date = new Date().toISOString().slice(0, 10);
  const choice = await dialog.showSaveDialog(mainWindow, {
    title: "Export JARVIS v4 Diagnostics",
    defaultPath: path.join(app.getPath("downloads"), `JARVIS-v4-diagnostics-${date}.json`),
    filters: [{ name: "JSON diagnostic report", extensions: ["json"] }],
    properties: ["showOverwriteConfirmation", "createDirectory"],
  });
  if (choice.canceled || !choice.filePath) return { success: false, canceled: true };
  const report = await createDiagnostics();
  fs.writeFileSync(choice.filePath, `${JSON.stringify(report, null, 2)}\n`, { mode: 0o600 });
  try { fs.chmodSync(choice.filePath, 0o600); } catch { /* Windows profile ACLs apply. */ }
  return { success: true, fileName: path.basename(choice.filePath) };
}

function voicePackDirectory() {
  return path.join(app.getPath("userData"), "voice-pack", "current");
}

function bundledVoicePackDirectory() {
  return app.isPackaged ? path.join(process.resourcesPath, "voice-pack") : "";
}

function updateVoicePreferenceFile({ replaceSystemVoice = false } = {}) {
  const target = path.join(app.getPath("userData"), "config", ".env");
  let contents = "";
  try { contents = fs.readFileSync(target, "utf8"); } catch { /* First launch. */ }

  const upsert = (key, value, replaceValues = []) => {
    const pattern = new RegExp(`^${key}=([^\\r\\n]*)$`, "m");
    const match = contents.match(pattern);
    if (!match) {
      contents += `${contents && !contents.endsWith("\n") ? "\n" : ""}${key}=${value}\n`;
    } else if (replaceValues.includes(match[1].trim().toLowerCase())) {
      contents = contents.replace(pattern, `${key}=${value}`);
    }
  };

  upsert("JARVIS_TTS_PROVIDER", "local", replaceSystemVoice ? ["system"] : []);
  upsert("JARVIS_VOICE_PACK", "current", replaceSystemVoice ? ["auto", "multilingual"] : []);
  fs.mkdirSync(path.dirname(target), { recursive: true, mode: 0o700 });
  const temporary = `${target}.tmp`;
  fs.writeFileSync(temporary, contents, { mode: 0o600 });
  fs.renameSync(temporary, target);
  try { fs.chmodSync(target, 0o600); } catch { /* Windows profile ACLs apply. */ }
}

function migrateLegacyVoicePackIfNeeded() {
  const destination = voicePackDirectory();
  if (fs.existsSync(path.join(destination, "voice-pack.json"))) return false;
  const legacy = path.join(app.getPath("appData"), "jarvis-v4-desktop", "voice-pack", "current");
  if (!fs.existsSync(path.join(legacy, "voice-pack.json"))) return false;
  fs.mkdirSync(path.dirname(destination), { recursive: true, mode: 0o700 });
  fs.renameSync(legacy, destination);
  // The old installation already had the user's chosen JARVIS voice. The new
  // stable app identity initially wrote the system-voice default, so restore
  // that explicit choice together with the pack migration.
  updateVoicePreferenceFile({ replaceSystemVoice: true });
  return true;
}

function readVoicePackManifest(directory = voicePackDirectory()) {
  try {
    const manifest = JSON.parse(fs.readFileSync(path.join(directory, "voice-pack.json"), "utf8"));
    return manifest && typeof manifest === "object" ? manifest : null;
  } catch {
    return null;
  }
}

function voicePackRequiredModels(manifest, platform = process.platform) {
  if (manifest?.engine_mode === "neutts-nano") {
    const pronunciationLibrary = platform === "win32"
      ? "espeak/espeak-ng.dll"
      : platform === "darwin"
        ? "espeak/libespeak-ng.1.52.0.1.dylib"
        : "espeak/libespeak-ng.so.1";
    return [
      "neutts-nano-german-Q4_0.gguf",
      "neutts-nano-Q4_0.gguf",
      "neucodec-int8.onnx",
      "NEUTTS_MODEL_LICENSE.txt",
      pronunciationLibrary,
      "espeak/espeak-ng-data/phondata",
      "espeak/espeak-ng-data/phontab",
      "espeak/espeak-ng-data/phonindex",
      "espeak/espeak-ng-data/de_dict",
      "espeak/espeak-ng-data/en_dict",
    ];
  }
  if (manifest?.engine_mode === "moss-nano") {
    return [
      "tts/config.json",
      "tts/model.safetensors",
      "tts/special_tokens_map.json",
      "tts/tokenizer.model",
      "tts/tokenizer_config.json",
      "audio-tokenizer/config.json",
      "audio-tokenizer/model-00001-of-00001.safetensors",
      "audio-tokenizer/model.safetensors.index.json",
    ];
  }
  return manifest?.engine_mode === "multilingual"
    ? ["ve.pt", "t3_mtl23ls_v2.safetensors", "s3gen.pt", "grapheme_mtl_merged_expanded_v1.json", "conds.pt"]
    : ["t3_turbo_v1.safetensors", "s3gen_meanflow.safetensors", "ve.safetensors"];
}

function voicePackProfileNames(manifest) {
  if (manifest?.engine_mode === "neutts-nano") {
    return ["profile-en.npy", "profile-de.npy", "profiles.json"];
  }
  const primary = manifest?.engine_mode === "moss-nano" ? "profile.safetensors" : "profile.pt";
  const profiles = [primary];
  if (
    manifest?.engine_mode === "moss-nano"
    && manifest?.voice_profiles?.de === "profile-de.safetensors"
  ) {
    profiles.push("profile-de.safetensors");
  }
  return profiles;
}

function voicePackStatus(directory = voicePackDirectory()) {
  const manifest = readVoicePackManifest(directory);
  const engineName = process.platform === "win32" ? "jarvis-voice-engine.exe" : "jarvis-voice-engine";
  const required = [
    path.join(directory, "bin", engineName),
    ...voicePackProfileNames(manifest).map((name) => path.join(directory, name)),
    ...voicePackRequiredModels(manifest).map((name) => path.join(directory, "models", name)),
  ];
  const compatible = Boolean(
    manifest
    && manifest.format_version === 1
    && (manifest.platform === process.platform || manifest.platform === "all")
    && (manifest.arch === process.arch || manifest.arch === "universal"),
  );
  return {
    installed: compatible && required.every((target) => fs.existsSync(target)),
    compatible,
    name: typeof manifest?.name === "string" ? manifest.name : "Offline Video Voice",
    version: typeof manifest?.version === "string" ? manifest.version : "",
    engineMode: typeof manifest?.engine_mode === "string" ? manifest.engine_mode : "",
    languages: Array.isArray(manifest?.languages) ? manifest.languages.filter((value) => value === "de" || value === "en") : [],
    platform: manifest?.platform || "",
    arch: manifest?.arch || "",
  };
}

function activeVoicePackDirectory() {
  const installed = voicePackDirectory();
  if (voicePackStatus(installed).installed) return installed;
  const bundled = bundledVoicePackDirectory();
  if (bundled && voicePackStatus(bundled).installed) return bundled;
  return "";
}

function enableBundledVoiceByDefault() {
  const bundled = bundledVoicePackDirectory();
  if (!bundled || !voicePackStatus(bundled).installed) return;
  // Add defaults only when the user has not chosen a provider yet. Existing
  // settings remain authoritative and a custom pack can still be installed.
  updateVoicePreferenceFile();
}

function isSafeRelativePath(value) {
  return typeof value === "string"
    && value.length > 0
    && !path.isAbsolute(value)
    && !value.split(/[\\/]+/).includes("..")
    && !value.includes("\0");
}

function findExtractedPackRoot(stagingDirectory) {
  if (fs.existsSync(path.join(stagingDirectory, "voice-pack.json"))) return stagingDirectory;
  const children = fs.readdirSync(stagingDirectory, { withFileTypes: true }).filter((entry) => entry.isDirectory());
  if (children.length === 1) {
    const nested = path.join(stagingDirectory, children[0].name);
    if (fs.existsSync(path.join(nested, "voice-pack.json"))) return nested;
  }
  throw new Error("This file is not a valid JARVIS voice pack.");
}

function validateExtractedTree(root) {
  const resolvedRoot = `${fs.realpathSync(root)}${path.sep}`;
  const pending = [root];
  let files = 0;
  let bytes = 0;
  const inventory = new Set();
  while (pending.length) {
    const directory = pending.pop();
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const target = path.join(directory, entry.name);
      const stat = fs.lstatSync(target);
      if (stat.isSymbolicLink()) throw new Error("Voice packs may not contain symbolic links.");
      const resolved = `${fs.realpathSync(target)}${stat.isDirectory() ? path.sep : ""}`;
      if (!resolved.startsWith(resolvedRoot)) throw new Error("Voice pack contains an unsafe path.");
      if (stat.isDirectory()) pending.push(target);
      else {
        files += 1;
        bytes += stat.size;
        inventory.add(path.relative(root, target).split(path.sep).join("/"));
        if (!withinVoicePackLimits(files, bytes)) {
          throw new Error("Voice pack exceeds the safety limit.");
        }
      }
    }
  }
  return inventory;
}

function sha256File(target) {
  return new Promise((resolve, reject) => {
    const hash = crypto.createHash("sha256");
    const stream = fs.createReadStream(target);
    stream.on("error", reject);
    stream.on("data", (chunk) => hash.update(chunk));
    stream.on("end", () => resolve(hash.digest("hex")));
  });
}

async function validateVoicePack(root) {
  const inventory = validateExtractedTree(root);
  const manifest = readVoicePackManifest(root);
  if (!manifest || manifest.format_version !== 1) throw new Error("Voice pack manifest is missing or incompatible.");
  if (!new Set(["turbo", "multilingual", "moss-nano", "neutts-nano"]).has(manifest.engine_mode)) {
    throw new Error("Voice pack declares an unsupported engine.");
  }
  if (
    !Array.isArray(manifest.languages)
    || manifest.languages.length < 1
    || manifest.languages.some((language) => language !== "de" && language !== "en")
  ) {
    throw new Error("Voice pack declares unsupported languages.");
  }
  if (manifest.platform !== process.platform && manifest.platform !== "all") {
    throw new Error(`This voice pack is for ${manifest.platform}, not ${process.platform}.`);
  }
  if (manifest.arch !== process.arch && manifest.arch !== "universal") {
    throw new Error(`This voice pack is for ${manifest.arch}, not ${process.arch}.`);
  }
  if (!manifest.files || typeof manifest.files !== "object") throw new Error("Voice pack checksums are missing.");
  for (const relative of inventory) {
    if (relative !== "voice-pack.json" && !Object.hasOwn(manifest.files, relative)) {
      throw new Error(`Voice pack contains an undeclared file: ${relative}`);
    }
  }
  for (const [relative, expected] of Object.entries(manifest.files)) {
    if (!isSafeRelativePath(relative) || !/^[a-f0-9]{64}$/i.test(String(expected))) {
      throw new Error("Voice pack contains an invalid checksum entry.");
    }
    const target = path.resolve(root, relative);
    if (!target.startsWith(`${path.resolve(root)}${path.sep}`) || !fs.statSync(target).isFile()) {
      throw new Error(`Voice pack file is missing: ${relative}`);
    }
    const actual = await sha256File(target);
    if (!crypto.timingSafeEqual(Buffer.from(actual), Buffer.from(String(expected).toLowerCase()))) {
      throw new Error(`Voice pack integrity check failed: ${relative}`);
    }
  }
  const engineName = process.platform === "win32" ? "jarvis-voice-engine.exe" : "jarvis-voice-engine";
  for (const relative of [
    `bin/${engineName}`,
    ...voicePackProfileNames(manifest),
    ...voicePackRequiredModels(manifest).map((name) => `models/${name}`),
  ]) {
    if (!Object.hasOwn(manifest.files, relative)) throw new Error(`Voice pack is incomplete: ${relative}`);
  }
  return manifest;
}

async function installVoicePack() {
  const choice = await dialog.showOpenDialog(mainWindow, {
    title: "Install JARVIS v4 Voice Pack",
    properties: ["openFile"],
    // macOS can grey out an unregistered custom `.jarvisvoice` extension when
    // it is used as a native file filter. Accept any file in the picker and
    // rely on the strict archive, size, path, platform, manifest and checksum
    // validation below before installing a single byte.
    filters: [{ name: "JARVIS v4 Voice Pack", extensions: ["*"] }],
  });
  if (choice.canceled || !choice.filePaths[0]) return { success: false, canceled: true };
  const archive = choice.filePaths[0];
  const archiveSize = fs.statSync(archive).size;
  if (archiveSize <= 0 || archiveSize > VOICE_PACK_MAX_BYTES) {
    return { success: false, error: "Voice pack file exceeds the safety limit." };
  }

  const userData = app.getPath("userData");
  const staging = fs.mkdtempSync(path.join(userData, "voice-pack-stage-"));
  let stopped = false;
  let backup = "";
  try {
    let extractedBytes = 0;
    let extractedFiles = 0;
    await extractZip(archive, {
      dir: staging,
      onEntry: (entry) => {
        if (!isSafeRelativePath(entry.fileName.replace(/\/$/, ""))) throw new Error("Voice pack contains an unsafe path.");
        extractedBytes += Number(entry.uncompressedSize || 0);
        extractedFiles += 1;
        if (!withinVoicePackLimits(extractedFiles, extractedBytes)) {
          throw new Error("Voice pack exceeds the safety limit.");
        }
      },
    });
    const root = findExtractedPackRoot(staging);
    const manifest = await validateVoicePack(root);
    const destinationParent = path.dirname(voicePackDirectory());
    const destination = voicePackDirectory();
    fs.mkdirSync(destinationParent, { recursive: true, mode: 0o700 });
    await stopBackend();
    stopped = true;
    if (fs.existsSync(destination)) {
      backup = path.join(destinationParent, `backup-${Date.now()}`);
      fs.renameSync(destination, backup);
    }
    fs.renameSync(root, destination);
    if (process.platform !== "win32") fs.chmodSync(path.join(destination, "bin", "jarvis-voice-engine"), 0o755);
    await startBackend();
    stopped = false;
    return { success: true, installed: true, name: manifest.name, version: manifest.version, backupCreated: Boolean(backup) };
  } catch (error) {
    const destination = voicePackDirectory();
    if (!fs.existsSync(destination) && backup && fs.existsSync(backup)) fs.renameSync(backup, destination);
    if (stopped) {
      try { await startBackend(); } catch { /* The original installation error is more useful. */ }
    }
    return { success: false, error: error instanceof Error ? error.message : String(error) };
  } finally {
    if (fs.existsSync(staging)) fs.rmSync(staging, { recursive: true, force: true });
  }
}

function isTrustedRenderer(webContents) {
  try {
    if (!mainWindow || webContents !== mainWindow.webContents || webContents.isDestroyed()) return false;
    const origin = new URL(webContents?.getURL() || "").origin;
    const appOrigin = new URL(DEV_URL || `http://127.0.0.1:${backendPort}`).origin;
    return origin === `http://127.0.0.1:${backendPort}` || origin === appOrigin;
  } catch {
    return false;
  }
}

function mediaAccessStatus(kind) {
  if (process.platform !== "darwin" || typeof systemPreferences.getMediaAccessStatus !== "function") {
    return "unknown";
  }
  try {
    return systemPreferences.getMediaAccessStatus(kind);
  } catch {
    return "unknown";
  }
}

function directoryAccessStatus(directory) {
  try {
    fs.accessSync(directory, fs.constants.R_OK | fs.constants.W_OK);
    return "granted";
  } catch {
    return "denied";
  }
}

function runAppleScriptProbe(applicationName, statement) {
  return new Promise((resolve) => {
    const child = spawn(
      "/usr/bin/osascript",
      ["-e", `tell application ${JSON.stringify(applicationName)} to ${statement}`],
      { stdio: ["ignore", "ignore", "pipe"] },
    );
    let errorText = "";
    const timer = setTimeout(() => child.kill(), 15000);
    child.stderr.on("data", (chunk) => { errorText += chunk.toString(); });
    child.once("error", () => {
      clearTimeout(timer);
      resolve("unavailable");
    });
    child.once("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) return resolve("granted");
      if (/not authorized|(-1743)/i.test(errorText)) return resolve("denied");
      return resolve("unavailable");
    });
  });
}

async function systemAccessStatus(probeAutomation = false) {
  const automation = process.platform === "darwin"
    ? { calendar: "unknown", mail: "unknown", notes: "unknown" }
    : { calendar: "unavailable", mail: "unavailable", notes: "unavailable" };
  if (process.platform === "darwin" && probeAutomation) {
    automation.calendar = await runAppleScriptProbe("Calendar", "count calendars");
    automation.mail = await runAppleScriptProbe("Mail", "count accounts");
    automation.notes = await runAppleScriptProbe("Notes", "count accounts");
  }
  const accessibility = process.platform === "darwin"
    ? (systemPreferences.isTrustedAccessibilityClient(false) ? "granted" : "not-granted")
    : "unknown";
  const userDirectories = [app.getPath("documents"), app.getPath("desktop"), app.getPath("downloads")];
  const files = userDirectories.every((directory) => directoryAccessStatus(directory) === "granted")
    ? "granted"
    : "limited";
  return {
    platform: process.platform,
    microphone: process.platform === "win32" ? "managed" : mediaAccessStatus("microphone"),
    screen: process.platform === "win32" ? "available" : mediaAccessStatus("screen"),
    accessibility,
    files,
    automation,
    setup: permissionSetupRecord(),
  };
}

async function requestMicrophoneAccess() {
  if (process.platform !== "darwin" || typeof systemPreferences.askForMediaAccess !== "function") {
    return mediaAccessStatus("microphone");
  }
  try {
    await systemPreferences.askForMediaAccess("microphone");
  } catch {
    // The current state is returned below and rendered with a Settings shortcut.
  }
  return mediaAccessStatus("microphone");
}

async function requestScreenAccess() {
  if (process.platform !== "darwin" || mediaAccessStatus("screen") === "granted") {
    return mediaAccessStatus("screen");
  }
  try {
    // macOS shows its own one-time Screen Recording consent sheet when the
    // first real capture is requested. A 1x1 thumbnail keeps the probe cheap.
    await desktopCapturer.getSources({ types: ["screen"], thumbnailSize: { width: 1, height: 1 } });
  } catch {
    // The status below tells the UI whether the user must finish in Settings.
  }
  return mediaAccessStatus("screen");
}

async function requestAllSystemAccess() {
  await requestMicrophoneAccess();
  await requestScreenAccess();

  if (process.platform === "darwin") {
    // The true flag asks macOS once and never bypasses its security controls.
    try { systemPreferences.isTrustedAccessibilityClient(true); } catch { /* Status is reported below. */ }
  }

  // These harmless reads trigger macOS's native one-time Apple Events sheets
  // for Calendar, Mail and Notes. The user's answer is then remembered by macOS.
  const status = await systemAccessStatus(true);
  writePrivateJson(permissionSetupPath(), {
    version: 1,
    completed: true,
    requestedAt: new Date().toISOString(),
    platform: process.platform,
  });
  status.setup = permissionSetupRecord();

  const needsManual = [];
  if (!new Set(["granted", "available", "managed"]).has(status.microphone)) needsManual.push("microphone");
  if (!new Set(["granted", "available", "managed"]).has(status.screen)) needsManual.push("screen");
  if (status.files !== "granted") needsManual.push("files");
  if (process.platform === "darwin" && status.accessibility !== "granted") needsManual.push("accessibility");
  if (process.platform === "darwin" && Object.values(status.automation).some((value) => value !== "granted")) needsManual.push("automation");

  // Some macOS permissions can only be enabled by the user. Open one central
  // Privacy & Security window instead of bouncing through several panes.
  let settingsOpened = false;
  if (process.platform === "darwin" && needsManual.length) {
    settingsOpened = (await openPrivacySettings("all")).success;
  }
  return { success: true, status, needsManual, settingsOpened };
}

async function openPrivacySettings(kind) {
  let target = "";
  if (process.platform === "darwin") {
    const panes = {
      microphone: "Privacy_Microphone",
      screen: "Privacy_ScreenCapture",
      automation: "Privacy_Automation",
      accessibility: "Privacy_Accessibility",
      files: "Privacy_AllFiles",
    };
    target = `x-apple.systempreferences:com.apple.preference.security?${panes[kind] || "Privacy"}`;
  } else if (process.platform === "win32") {
    const panes = {
      microphone: "ms-settings:privacy-microphone",
      files: "ms-settings:privacy-broadfilesystemaccess",
      accessibility: "ms-settings:easeofaccess",
      all: "ms-settings:privacy",
    };
    target = panes[kind] || "ms-settings:privacy";
  } else if (process.platform === "linux") {
    const candidates = kind === "microphone"
      ? [["gnome-control-center", ["privacy"]], ["systemsettings6", []], ["systemsettings5", []], ["systemsettings", []]]
      : [["gnome-control-center", ["privacy"]], ["systemsettings6", []], ["systemsettings5", []], ["systemsettings", []]];
    for (const [command, args] of candidates) {
      const launched = await new Promise((resolve) => {
        const child = spawn(command, args, { detached: true, stdio: "ignore" });
        child.once("spawn", () => { child.unref(); resolve(true); });
        child.once("error", () => resolve(false));
      });
      if (launched) return { success: true };
    }
    return { success: false, error: "No supported Linux settings application was found." };
  }
  if (!target) return { success: false, error: "Open the operating system privacy settings manually." };
  try {
    await shell.openExternal(target);
    return { success: true };
  } catch (error) {
    return { success: false, error: error instanceof Error ? error.message : String(error) };
  }
}

function constantTimeTextEqual(left, right) {
  const a = Buffer.from(String(left || ""));
  const b = Buffer.from(String(right || ""));
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

async function authorizeGoogleAccount(clientId, clientSecret) {
  if (googleOAuthInProgress) throw new Error("A Google connection is already in progress.");
  googleOAuthInProgress = true;
  const validatedClientId = validateClientId(clientId);
  const { verifier, challenge, state } = createPkce();
  let callbackServer;
  let timeout;
  try {
    const result = await new Promise((resolve, reject) => {
      let settled = false;
      const finish = (error, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timeout);
        callbackServer?.close();
        if (error) reject(error);
        else resolve(value);
      };
      callbackServer = http.createServer(async (request, response) => {
        try {
          const url = new URL(request.url || "/", "http://127.0.0.1");
          if (url.pathname !== "/") {
            response.writeHead(404, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" });
            response.end("Not found");
            return;
          }
          if (!constantTimeTextEqual(url.searchParams.get("state"), state)) {
            throw new Error("Google returned an invalid security state.");
          }
          if (url.searchParams.get("error")) throw new Error("Google account access was not granted.");
          const code = url.searchParams.get("code") || "";
          if (!code || code.length > 4096) throw new Error("Google returned an invalid authorization code.");
          const address = callbackServer.address();
          const port = typeof address === "object" && address ? address.port : 0;
          const redirectUri = `http://127.0.0.1:${port}`;
          const token = await exchangeAuthorizationCode({
            clientId: validatedClientId,
            clientSecret,
            redirectUri,
            code,
            verifier,
          });
          response.writeHead(200, {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "no-store",
            "X-Frame-Options": "DENY",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
          });
          response.end("<!doctype html><meta charset=utf-8><title>JARVIS connected</title><style>body{margin:0;background:#03070d;color:#dff7ff;font:16px system-ui;display:grid;min-height:100vh;place-items:center}main{padding:32px;border:1px solid #17445a;border-radius:18px;background:#07121d;text-align:center}p{color:#8cb8c9}</style><main><h1>Google connected</h1><p>You can close this tab and return to JARVIS v4.</p></main>");
          finish(null, token);
        } catch (error) {
          response.writeHead(400, { "Content-Type": "text/plain; charset=utf-8", "Cache-Control": "no-store" });
          response.end("Google connection failed. Return to JARVIS v4 and try again.");
          finish(error);
        }
      });
      callbackServer.on("error", finish);
      callbackServer.listen(0, "127.0.0.1", async () => {
        try {
          const address = callbackServer.address();
          const port = typeof address === "object" && address ? address.port : 0;
          if (!port) throw new Error("Could not start the private Google callback.");
          const redirectUri = `http://127.0.0.1:${port}`;
          const authorizationUrl = buildAuthorizationUrl({
            clientId: validatedClientId,
            redirectUri,
            challenge,
            state,
          });
          await shell.openExternal(authorizationUrl);
        } catch (error) {
          finish(error);
        }
      });
      timeout = setTimeout(() => finish(new Error("Google connection timed out.")), 180000);
    });
    return result;
  } finally {
    clearTimeout(timeout);
    callbackServer?.close();
    googleOAuthInProgress = false;
  }
}

async function connectGoogleAccount(values) {
  const storageMode = normalizeStorageMode(values?.storageMode || currentStorageMode());
  if (storageMode === "keychain" && !secureStorageAvailable()) {
    return { success: false, error: "Secure operating-system storage is unavailable." };
  }
  const clientId = validateClientId(values?.clientId);
  const clientSecret = typeof values?.clientSecret === "string" ? values.clientSecret.trim() : "";
  if (clientSecret.length > 2048 || /[\r\n\0]/.test(clientSecret)) {
    return { success: false, error: "Invalid Google OAuth client secret." };
  }
  const { refreshToken } = await authorizeGoogleAccount(clientId, clientSecret);
  const store = storageMode === "local" ? readLocalSecretStore() : readSecretStore();
  storeSecretValue(store, "googleOauthClientId", clientId, storageMode);
  if (clientSecret) storeSecretValue(store, "googleOauthClientSecret", clientSecret, storageMode);
  storeSecretValue(store, "googleRefreshToken", refreshToken, storageMode);
  if (storageMode === "local") writeLocalSecretStore(store);
  else writeSecretStore(store);
  writeStorageMode(storageMode);
  await restartBackend();
  return { success: true, storageMode };
}

async function disconnectGoogleAccount() {
  const secrets = resolvedSecrets();
  if (!secrets.googleRefreshToken) return { success: true, connected: false };
  if (process.env.GOOGLE_REFRESH_TOKEN && !readSecretStore().googleRefreshToken && !readLocalSecretStore().googleRefreshToken) {
    return { success: false, error: "This Google connection is managed by an environment variable." };
  }
  const choice = await dialog.showMessageBox(mainWindow, {
    type: "warning",
    title: "Disconnect Google account?",
    message: "Disconnect Gmail and Google Calendar from JARVIS v4?",
    detail: "The local refresh token will be removed and the Google grant will be revoked. Your Gmail messages and calendar events are not deleted.",
    buttons: ["Cancel", "Disconnect"],
    defaultId: 0,
    cancelId: 0,
    noLink: true,
  });
  if (choice.response !== 1) return { success: false, canceled: true };
  const revoked = await revokeToken(secrets.googleRefreshToken);
  if (!revoked) return { success: false, error: "Google could not revoke the account grant. Nothing was removed." };
  for (const [reader, writer] of [[readSecretStore, writeSecretStore], [readLocalSecretStore, writeLocalSecretStore]]) {
    const store = reader();
    delete store.googleOauthClientId;
    delete store.googleOauthClientSecret;
    delete store.googleRefreshToken;
    writer(store);
  }
  await restartBackend();
  return { success: true, connected: false };
}

function configureIpc() {
  ipcMain.on("runtime:get", (event) => {
    event.returnValue = isTrustedRenderer(event.sender)
      ? runtimeConfig()
      : {
        apiBase: "",
        authToken: "",
        desktop: true,
        development: false,
        platform: process.platform,
        arch: process.arch,
        appVersion: app.getVersion(),
      };
  });
  ipcMain.handle("secrets:status", (event) => (
    isTrustedRenderer(event.sender)
      ? secretStorageStatus()
      : {
        mode: "keychain",
        requiresPassword: false,
        storageBackend: "unavailable",
        secureStorageAvailable: false,
        hasLocalSecrets: false,
        hasKeychainSecrets: false,
      }
  ));
  ipcMain.handle("backend:restart", async (event) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    try {
      await restartBackend();
      return { success: true };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  ipcMain.handle("performance:set-voice-active", (event, active) => {
    if (!isTrustedRenderer(event.sender)) return { success: false };
    // Hidden Chromium renderers are throttled by default. On Windows this can
    // interrupt an always-on microphone, so disable throttling only for the
    // duration of a live voice session and keep the normal efficient default
    // for idle/background windows.
    if (process.platform === "win32" && mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.webContents.setBackgroundThrottling(active !== true);
    }
    return { success: true };
  });
  ipcMain.handle("secrets:activate-storage", async (event, mode) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    try {
      return await activateStoredSecretMode(mode);
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  ipcMain.handle("privacy:delete-all-data", async (event) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    try {
      return await deleteAllLocalData();
    } catch (error) {
      try { await startBackend(); } catch { /* Keep the deletion error as the primary message. */ }
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  ipcMain.handle("permissions:status", async (event, options) => (
    isTrustedRenderer(event.sender)
      ? systemAccessStatus(Boolean(options?.probeAutomation))
      : { platform: process.platform, microphone: "unknown", screen: "unknown", accessibility: "unknown", files: "unknown", automation: { calendar: "unknown", mail: "unknown", notes: "unknown" } }
  ));
  ipcMain.handle("permissions:request-microphone", async (event) => (
    isTrustedRenderer(event.sender) ? requestMicrophoneAccess() : "denied"
  ));
  ipcMain.handle("permissions:request-all", async (event) => (
    isTrustedRenderer(event.sender)
      ? requestAllSystemAccess()
      : { success: false, error: "Untrusted request." }
  ));
  ipcMain.handle("permissions:open-settings", async (event, kind) => (
    isTrustedRenderer(event.sender)
      ? openPrivacySettings(String(kind || ""))
      : { success: false, error: "Untrusted request." }
  ));
  ipcMain.handle("google:connect", async (event, values) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    try {
      return await connectGoogleAccount(values);
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  ipcMain.handle("google:disconnect", async (event) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    try {
      return await disconnectGoogleAccount();
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  ipcMain.handle("voice-pack:status", (event) => {
    if (!isTrustedRenderer(event.sender)) return { installed: false, compatible: false };
    return voicePackStatus(activeVoicePackDirectory() || voicePackDirectory());
  });
  ipcMain.handle("voice-pack:install", async (event) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    return installVoicePack();
  });
  ipcMain.handle("support:diagnostics", async (event) => (
    isTrustedRenderer(event.sender)
      ? createDiagnostics()
      : { error: "Untrusted request." }
  ));
  ipcMain.handle("support:export-diagnostics", async (event) => {
    if (!isTrustedRenderer(event.sender)) return { success: false, error: "Untrusted request." };
    try {
      return await exportDiagnostics();
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
  ipcMain.handle("secrets:save", async (event, values) => {
    if (!isTrustedRenderer(event.sender)) {
      return { success: false, error: "Untrusted request." };
    }
    const storageMode = normalizeStorageMode(values?.storageMode || currentStorageMode());
    if (storageMode === "keychain" && !secureStorageAvailable()) {
      return {
        success: false,
        storageBackend: selectedStorageBackend(),
        error: "Secure operating-system storage is unavailable. Set API keys as environment variables instead.",
      };
    }
    const store = storageMode === "local" ? readLocalSecretStore() : readSecretStore();
    for (const definition of SECRET_DEFINITIONS) {
      const rawValue = values?.[definition.output];
      if (typeof rawValue === "string" && (rawValue.length > 16384 || /[\r\n\0]/.test(rawValue))) {
        return { success: false, error: "API keys must be a single line of at most 16,384 characters." };
      }
      const value = meaningfulSecret(rawValue);
      if (value) {
        store[definition.store] = storageMode === "local"
          ? value
          : safeStorage.encryptString(value).toString("base64");
      }
    }
    if (storageMode === "local") writeLocalSecretStore(store);
    else writeSecretStore(store);
    writeStorageMode(storageMode);
    try {
      await restartBackend();
      return {
        success: true,
        storageMode,
        storageBackend: storageMode === "local" ? "private-local-file" : selectedStorageBackend(),
      };
    } catch (error) {
      return { success: false, error: error instanceof Error ? error.message : String(error) };
    }
  });
}

function focusMainWindow() {
  return focusExistingWindow(mainWindow);
}

function desktopWindowIcon() {
  return app.isPackaged
    ? path.join(process.resourcesPath, "app-icon.png")
    : path.join(PROJECT_ROOT, "assets", "icon.png");
}

function createWindow() {
  // This function can be reached from startup, OS activation and a second
  // launch request. Treat it as "ensure one window" so those events can never
  // create multiple JARVIS tabs/windows for the same user profile.
  if (focusMainWindow()) return mainWindow;
  // The interface is dark at every size, so the window furniture has to be as
  // well. Without this the title bar area follows the system appearance and
  // shows up as a pale strip above the app on a machine set to light mode.
  nativeTheme.themeSource = "dark";
  mainWindow = new BrowserWindow({
    darkTheme: true,
    width: 1120,
    height: 760,
    minWidth: 720,
    minHeight: 600,
    show: false,
    backgroundColor: "#050508",
    title: "JARVIS v4",
    icon: desktopWindowIcon(),
    titleBarStyle: process.platform === "darwin"
      ? "hiddenInset"
      : process.platform === "win32"
        ? "hidden"
        : "default",
    titleBarOverlay: process.platform === "win32"
      ? { color: "#050508", symbolColor: "#7dd3fc", height: 44 }
      : undefined,
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      webSecurity: true,
      webviewTag: false,
      allowRunningInsecureContent: false,
      navigateOnDragDrop: false,
      // Idle/minimized windows stay efficient. The trusted voice-session IPC
      // temporarily lifts this only on Windows while the microphone is live.
      backgroundThrottling: true,
    },
  });

  const appUrl = DEV_URL || `http://127.0.0.1:${backendPort}/`;
  const allowedOrigins = new Set([new URL(appUrl).origin, `http://127.0.0.1:${backendPort}`]);
  mainWindow.webContents.on("will-navigate", (event, targetUrl) => {
    try {
      const target = new URL(targetUrl);
      if (!allowedOrigins.has(target.origin) || target.pathname !== "/") event.preventDefault();
    } catch {
      event.preventDefault();
    }
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    try {
      const target = new URL(url);
      if (
        target.protocol === "https:"
        && !target.username
        && !target.password
        && target.href.length <= 4096
      ) {
        void shell.openExternal(target.href);
      }
    } catch {
      // Malformed and non-HTTPS popup targets stay inside the deny path.
    }
    return { action: "deny" };
  });
  mainWindow.once("ready-to-show", () => mainWindow?.show());
  mainWindow.on("closed", () => { mainWindow = null; });
  void mainWindow.loadURL(appUrl);
  return mainWindow;
}

function showSettings() {
  if (!mainWindow) return;
  if (mainWindow.isMinimized()) mainWindow.restore();
  mainWindow.show();
  mainWindow.focus();
  mainWindow.webContents.send("ui:open-settings");
}

const LEGAL_DOCUMENTS = Object.freeze({
  privacy: "PRIVACY.md",
  support: "SUPPORT.md",
  guide: "USER_GUIDE.md",
  licenses: "THIRD_PARTY_COMPONENTS.json",
});

async function openLegalDocument(kind) {
  const filename = LEGAL_DOCUMENTS[kind];
  if (!filename) return;
  const root = app.isPackaged
    ? path.join(process.resourcesPath, "legal")
    : path.join(__dirname, "legal-dist");
  const target = path.join(root, filename);
  if (!fs.existsSync(target)) {
    dialog.showErrorBox("Document unavailable", "Rebuild JARVIS v4 to generate its customer documents.");
    return;
  }
  const error = await shell.openPath(target);
  if (error) dialog.showErrorBox("Could not open document", error);
}

function configureApplicationMenu() {
  const settingsItem = {
    label: "Settings…",
    accelerator: "CmdOrCtrl+,",
    click: showSettings,
  };
  const helpMenu = {
    label: "Help",
    submenu: [
      { label: "User Guide", click: () => void openLegalDocument("guide") },
      { label: "Privacy", click: () => void openLegalDocument("privacy") },
      { label: "Support", click: () => void openLegalDocument("support") },
      { label: "Third-Party Licenses", click: () => void openLegalDocument("licenses") },
      { type: "separator" },
      { role: "about" },
    ],
  };
  const template = process.platform === "darwin"
    ? [
      {
        label: app.name,
        submenu: [
          { role: "about" },
          { type: "separator" },
          settingsItem,
          { type: "separator" },
          { role: "services" },
          { type: "separator" },
          { role: "hide" },
          { role: "hideOthers" },
          { role: "unhide" },
          { type: "separator" },
          { role: "quit" },
        ],
      },
      { role: "editMenu" },
      { role: "viewMenu" },
      { role: "windowMenu" },
      helpMenu,
    ]
    : [
      { label: "File", submenu: [settingsItem, { type: "separator" }, { role: "quit" }] },
      { role: "editMenu" },
      { role: "viewMenu" },
      { role: "windowMenu" },
      helpMenu,
    ];
  Menu.setApplicationMenu(Menu.buildFromTemplate(template));
}

// Keep one desktop shell and one local backend per user profile. Multiple
// Electron instances otherwise compete for the same settings and can each
// start a heavyweight offline voice engine, making the voice appear broken.
const hasSingleInstanceLock = app.requestSingleInstanceLock();
if (!hasSingleInstanceLock) {
  app.quit();
} else {
  app.on("second-instance", () => {
    if (!focusMainWindow() && app.isReady() && backendPort) createWindow();
  });

  app.whenReady().then(async () => {
    app.setAboutPanelOptions({
      applicationName: "JARVIS v4",
      applicationVersion: app.getVersion(),
      version: `Version ${app.getVersion()}`,
      copyright: "Independent local AI assistant",
    });
    configureIpc();
    session.defaultSession.setPermissionCheckHandler((webContents, permission) => {
      return permission === "media" && isTrustedRenderer(webContents);
    });
    session.defaultSession.setPermissionRequestHandler((webContents, permission, callback, details) => {
      const mediaTypes = Array.isArray(details?.mediaTypes) ? details.mediaTypes : [];
      const audioOnly = mediaTypes.length === 0 || mediaTypes.every((type) => type === "audio");
      callback(permission === "media" && isTrustedRenderer(webContents) && audioOnly);
    });
    try {
      migrateLegacyVoicePackIfNeeded();
      enableBundledVoiceByDefault();
      await startBackend();
      createWindow();
      configureApplicationMenu();
    } catch (error) {
      dialog.showErrorBox(
        "JARVIS v4 could not start",
        `${error instanceof Error ? error.message : String(error)}\n\nDevelopment requires Python 3.11+ and the verified packages from requirements-build.lock.txt.`,
      );
      app.quit();
    }
  });

  app.on("activate", () => { if (backendPort) createWindow(); });
  app.on("window-all-closed", () => { if (process.platform !== "darwin") app.quit(); });
  app.on("before-quit", () => { if (backendProcess) backendProcess.kill(); });
}
