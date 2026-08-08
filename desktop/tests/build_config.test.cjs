"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const desktopRoot = path.resolve(__dirname, "..");
const manifest = JSON.parse(fs.readFileSync(path.join(desktopRoot, "package.json"), "utf8"));
const afterPack = require("../scripts/after_pack.cjs");

test("macOS release processes receive microphone and requested Apple automation rights", () => {
  for (const file of ["entitlements.mac.plist", "entitlements.mac.inherit.plist"]) {
    const contents = fs.readFileSync(path.join(desktopRoot, "build", file), "utf8");
    assert.match(contents, /<key>com\.apple\.security\.device\.audio-input<\/key>\s*<true\/>/);
    assert.match(contents, /<key>com\.apple\.security\.automation\.apple-events<\/key>\s*<true\/>/);
  }
});

test("ad-hoc candidates sign the backend with inherited automation entitlements", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "scripts", "after_pack.cjs"), "utf8");
  assert.match(source, /entitlements\.mac\.inherit\.plist/);
  // The backend ships as a PyInstaller directory build, so the executable sits
  // one level inside the copied "backend" resource. Both that nested path and
  // the older flat one must stay resolvable, or the signing step would target
  // a file that is not there and ship an unsigned sidecar.
  assert.match(source, /"Resources", "backend"/);
  assert.match(source, /"jarvis-server", "jarvis-server"/);
  assert.match(source, /existsSync\(nestedBackend\)/);
});

test("desktop packaging declares microphone purpose and Windows installer support", () => {
  assert.match(manifest.build.mac.extendInfo.NSMicrophoneUsageDescription, /microphone/i);
  assert.equal(manifest.build.mac.minimumSystemVersion, "14.0");
  assert.equal(manifest.build.win.target[0].target, "nsis");
  assert.deepEqual(manifest.build.win.target[0].arch, ["x64"]);
  assert.equal(manifest.build.win.icon, "../assets/icon.ico");
  assert.equal(manifest.build.win.requestedExecutionLevel, "asInvoker");
  assert.equal(manifest.build.nsis.oneClick, false);
  assert.equal(manifest.build.nsis.allowToChangeInstallationDirectory, true);
  assert.deepEqual(manifest.build.nsis.installerLanguages, ["de_DE", "en_US"]);
  assert.equal(manifest.build.nsis.installerIcon, "../assets/icon.ico");
  assert.equal(manifest.build.nsis.installerSidebar, "../assets/installer-sidebar.bmp");
  const sidebar = fs.readFileSync(path.resolve(desktopRoot, "..", "assets", "installer-sidebar.bmp"));
  assert.equal(sidebar.subarray(0, 2).toString("ascii"), "BM");
  assert.equal(sidebar.readInt32LE(18), 164);
  assert.equal(Math.abs(sidebar.readInt32LE(22)), 314);
  assert.equal(sidebar.readUInt16LE(28), 24);
  assert.equal(manifest.build.nsis.createDesktopShortcut, "always");
  assert.equal(manifest.build.nsis.deleteAppDataOnUninstall, true);
});

test("Linux ships installable packages with a local speech fallback", () => {
  const targets = manifest.build.linux.target.map((entry) => entry.target);
  assert.deepEqual(targets, ["AppImage", "deb"]);
  assert.ok(manifest.build.deb.depends.includes("espeak-ng"));
  assert.equal(manifest.build.linux.icon, "../assets/icon.png");
  assert.equal(manifest.desktopName, "jarvis-v4-desktop.desktop");
  assert.equal(manifest.build.linux.syncDesktopName, true);
  assert.equal(manifest.homepage, "https://github.com/samirtest378/jarvis-v4");
  assert.equal(manifest.repository.url, "https://github.com/samirtest378/jarvis-v4.git");
});

test("desktop privacy shortcuts cover Windows known folders and Linux settings", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(source, /ms-settings:privacy-broadfilesystemaccess/);
  assert.match(source, /process\.platform === "linux"/);
  assert.match(source, /gnome-control-center/);
  assert.match(source, /systemsettings6/);
});

test("one-time permission setup is persisted and requests every macOS capability together", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  const preload = fs.readFileSync(path.join(desktopRoot, "preload.cjs"), "utf8");
  assert.match(source, /permissions-setup\.json/);
  assert.match(source, /permissions:request-all/);
  assert.match(source, /desktopCapturer\.getSources/);
  assert.match(source, /isTrustedAccessibilityClient\(true\)/);
  assert.match(source, /systemAccessStatus\(true\)/);
  assert.match(preload, /requestAllSystemAccess/);
});

test("Windows launches share one app identity, one window and the current logo", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(source, /requestSingleInstanceLock\(\)/);
  assert.match(source, /app\.on\("second-instance"/);
  assert.match(source, /if \(focusMainWindow\(\)\) return mainWindow/);
  assert.match(source, /setAppUserModelId\("ai\.jarvis\.v4"\)/);
  assert.match(source, /icon: desktopWindowIcon\(\)/);
  assert.match(source, /process\.platform === "win32"\s*\? "hidden"/);
  assert.match(source, /titleBarOverlay: process\.platform === "win32"/);
  assert.match(source, /symbolColor: "#7dd3fc"/);
  const iconResource = manifest.build.extraResources.find((entry) => entry.to === "app-icon.png");
  assert.equal(iconResource?.from, "../assets/icon.png");

  const icon = fs.readFileSync(path.resolve(desktopRoot, "..", "assets", "icon.ico"));
  assert.equal(icon.readUInt16LE(0), 0);
  assert.equal(icon.readUInt16LE(2), 1);
  assert.ok(icon.readUInt16LE(4) >= 7, "Windows icon must contain taskbar and shortcut sizes");
});

test("Google consent can use the packaged OAuth client and reconnect stays one click", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(source, /values\?\.clientId \|\| configured\.googleOauthClientId/);
  assert.match(source, /requestedSecret \|\| configured\.googleOauthClientSecret/);
  const disconnectBody = source.match(/async function disconnectGoogleAccount\(\)[\s\S]*?return \{ success: true, connected: false \};\n\}/)?.[0] || "";
  assert.match(disconnectBody, /delete store\.googleRefreshToken/);
  assert.doesNotMatch(disconnectBody, /delete store\.googleOauthClientId/);
  assert.doesNotMatch(disconnectBody, /delete store\.googleOauthClientSecret/);
});

test("Windows voice capture stays smooth without wasting idle CPU", () => {
  const mainSource = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  const preloadSource = fs.readFileSync(path.join(desktopRoot, "preload.cjs"), "utf8");
  const voiceSource = fs.readFileSync(path.resolve(desktopRoot, "..", "frontend", "src", "voice.ts"), "utf8");
  const worklet = path.resolve(desktopRoot, "..", "frontend", "public", "audio-capture-worklet.js");
  assert.equal(fs.existsSync(worklet), true);
  assert.match(fs.readFileSync(worklet, "utf8"), /registerProcessor\("jarvis-audio-capture"/);
  assert.match(voiceSource, /new AudioWorkletNode/);
  assert.match(voiceSource, /setVoiceActivity\(enabled\)/);
  assert.match(preloadSource, /performance:set-voice-active/);
  assert.match(mainSource, /backgroundThrottling: true/);
  assert.match(mainSource, /setBackgroundThrottling\(active !== true\)/);
  assert.match(mainSource, /process\.platform === "win32"/);
});

test("desktop renderer and navigation use a narrow security boundary", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(source, /contextIsolation:\s*true/);
  assert.match(source, /nodeIntegration:\s*false/);
  assert.match(source, /sandbox:\s*true/);
  assert.match(source, /webSecurity:\s*true/);
  assert.match(source, /webviewTag:\s*false/);
  assert.match(source, /allowRunningInsecureContent:\s*false/);
  assert.match(source, /navigateOnDragDrop:\s*false/);
  assert.match(source, /webContents !== mainWindow\.webContents/);
  assert.match(source, /target\.protocol === "https:"/);
  assert.match(source, /target\.pathname !== "\/"/);
});

test("desktop releases include a separately built offline speech runtime", () => {
  const speechResource = manifest.build.extraResources.find((entry) => entry.to === "speech-runtime");
  assert.ok(speechResource, "speech-runtime extraResource is required");
  assert.equal(speechResource.from, "speech-runtime");
  assert.match(manifest.scripts.build, /build:speech/);
  assert.match(manifest.scripts["build:dir"], /build:speech/);
});

test("the Windows installer embeds the verified Windows bilingual voice", () => {
  const voiceResource = manifest.build.extraResources.find((entry) => entry.to === "voice-pack");
  assert.ok(voiceResource, "bundled voice-pack resource is required");
  assert.equal(voiceResource.from, "bundled-voice-pack");
  const workflow = fs.readFileSync(path.resolve(desktopRoot, "..", ".github", "workflows", "build-installers.yml"), "utf8");
  assert.match(workflow, /stage_bundled_voice_pack\.py/);
  assert.match(workflow, /--platform win32/);
  assert.match(workflow, /--arch x64/);
  assert.match(workflow, /VOICE_RELEASE_TAG: v4\.1\.1/);
  assert.match(workflow, /JARVIS-v4-Smooth-Bilingual-Voice-4\.1\.1-win32-x64\.jarvisvoice/);
});

test("desktop selects the bundled native voice and migrates the previous Mac pack", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(source, /function activeVoicePackDirectory\(\)/);
  assert.match(source, /env\.JARVIS_LOCAL_VOICE_PACK = activeVoicePack/);
  assert.match(source, /jarvis-v4-desktop", "voice-pack", "current"/);
  assert.match(source, /hasCustomVoicePackMarker/);
  assert.match(source, /bundled-activation\.json/);
  assert.match(source, /updateVoicePreferenceFile\(\{ forceLocalVoice: true \}\)/);
  assert.match(source, /enableBundledVoiceByDefault\(\)/);
});

test("desktop releases include customer documents and third-party license evidence", () => {
  const legalResource = manifest.build.extraResources.find((entry) => entry.to === "legal");
  assert.ok(legalResource, "legal extraResource is required");
  assert.equal(legalResource.from, "legal-dist");
  const buildSource = fs.readFileSync(path.resolve(desktopRoot, "..", "scripts", "build_backend.py"), "utf8");
  assert.match(buildSource, /collect_legal_notices/);
  const mainSource = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(mainSource, /Third-Party Licenses/);
  assert.match(mainSource, /USER_GUIDE\.md/);
  assert.match(mainSource, /PRIVACY\.md/);
  assert.match(mainSource, /SUPPORT\.md/);
});

test("the packaging hook verifies the copied speech runtime and pinned model", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "scripts", "after_pack.cjs"), "utf8");
  assert.equal(typeof afterPack.assertSpeechRuntime, "function");
  assert.match(source, /assertSpeechRuntime\(context\)/);
  assert.match(source, /317eb69c11673c9de1e1f0d459b253999804ec71ac4c23c17ecf5fbe24e259a1/);
  assert.match(source, /ggml-large-v3-turbo-q8_0\.bin/);
  assert.match(source, /ggml-silero-v6\.2\.0\.bin/);
  assert.match(source, /2aa269b785eeb53a82983a20501ddf7c1d9c48e33ab63a41391ac6c9f7fb6987/);
  assert.match(source, /WHISPER_CPP_LICENSE\.txt/);
  assert.match(source, /whisper-server\.exe/);
});

test("the cross-platform package guard pins the same models and German profile", () => {
  const source = fs.readFileSync(path.join(desktopRoot, "scripts", "after_pack.cjs"), "utf8");
  assert.equal(typeof afterPack.assertBundledVoice, "function");
  assert.match(source, /profile-de\.npy.*03d0612714da53a5851368fa03497397bcc4ccd39b46f2cd343b7b9d4d25a191/s);
  assert.match(source, /Bundled voice identity differs across platforms/);
});

test("voice-pack validation accepts only the declared local model family", () => {
  const mainSource = fs.readFileSync(path.join(desktopRoot, "main.cjs"), "utf8");
  assert.match(mainSource, /voicePackRequiredModels/);
  assert.match(mainSource, /engine_mode === "multilingual"/);
  assert.match(mainSource, /t3_mtl23ls_v2\.safetensors/);
  assert.match(mainSource, /grapheme_mtl_merged_expanded_v1\.json/);
  assert.match(mainSource, /engine_mode === "moss-nano"/);
  assert.match(mainSource, /MOSS-TTS-Nano-100M|model-00001-of-00001\.safetensors/);
  assert.match(mainSource, /profile\.safetensors/);
  assert.match(mainSource, /engine_mode === "neutts-nano"/);
  assert.match(mainSource, /neutts-nano-german-Q4_0\.gguf/);
  assert.match(mainSource, /neucodec-int8\.onnx/);
  assert.match(mainSource, /profile-en\.npy/);
  assert.match(mainSource, /unsupported engine/);
  assert.match(mainSource, /undeclared file/);
});

test("unpacked build apps are excluded from Spotlight app discovery", (t) => {
  const appOutDir = fs.mkdtempSync(path.join(os.tmpdir(), "jarvis-build-output-"));
  t.after(() => fs.rmSync(appOutDir, { recursive: true, force: true }));
  afterPack.markBuildOutputNonIndexable({ appOutDir });
  assert.equal(fs.existsSync(path.join(appOutDir, ".metadata_never_index")), true);
});

test("release automation is Windows-only and cannot publish an unsigned sale build", () => {
  const projectRoot = path.resolve(desktopRoot, "..");
  const workflow = fs.readFileSync(path.join(projectRoot, ".github", "workflows", "build-installers.yml"), "utf8");
  const publisher = fs.readFileSync(path.join(projectRoot, ".github", "workflows", "publish-installers.yml"), "utf8");
  const smoke = fs.readFileSync(path.join(projectRoot, "scripts", "verify_windows_installer.ps1"), "utf8");

  for (const releaseWorkflow of [workflow, publisher]) {
    assert.match(releaseWorkflow, /windows-2025/);
    assert.doesNotMatch(releaseWorkflow, /macos-15|ubuntu-24\.04|AppImage|\.deb/);
    assert.match(releaseWorkflow, /jarvis-v4-windows-x64/);
    assert.doesNotMatch(releaseWorkflow, /JARVIS-v3|jarvis-v3|JARVIS v3/);
  }
  assert.match(workflow, /name: Windows x64 sale installer/);
  assert.match(workflow, /compression-level: 0/);
  assert.match(workflow, /npm --prefix desktop run build:speech/);
  assert.match(workflow, /npm --prefix desktop run build -- --win/);
  assert.match(workflow, /--publish never/);
  assert.match(workflow, /Build signed installer[\s\S]*CSC_LINK: \$\{\{ secrets\.WIN_CSC_LINK \}\}/);
  assert.match(workflow, /Clean-install and launch the Windows app[\s\S]*verify_windows_installer\.ps1/);
  assert.doesNotMatch(workflow, /gh release upload|gh release create/);
  assert.match(workflow, /Build JARVIS v4 installers/);

  assert.match(publisher, /Get-AuthenticodeSignature/);
  assert.match(publisher, /actions\/setup-python@v5/);
  assert.match(publisher, /Require commercial release evidence[\s\S]*release:audit:strict/);
  assert.match(publisher, /signature\.Status -ne "Valid"/);
  assert.match(publisher, /Bind evidence to the exact installer[\s\S]*Get-FileHash/);
  assert.match(publisher, /WINDOWS_SIGNING_CONFIRMATION\.md/);
  assert.match(publisher, /RELEASE_QA_CONFIRMATION\.md/);
  assert.match(publisher, /Verify the source workflow run[\s\S]*run\.conclusion -ne "success"/);
  assert.match(publisher, /gh release create/);
  assert.match(publisher, /RELEASE_NOTES_4\.1\.2\.md/);
  assert.match(publisher, /verify_windows_installer\.ps1 -InstallerPath \$installer -RequireSignature/);
  assert.match(publisher, /actions\/checkout@v4/);

  assert.match(smoke, /ggml-large-v3-turbo-q8_0\.bin/);
  assert.match(smoke, /ggml-silero-v6\.2\.0\.bin/);
  assert.match(smoke, /exceeds GitHub's 2 GiB release-asset limit/);
  assert.match(smoke, /accelerators\)\.Count -ne 1/);
  assert.match(smoke, /languages\) -contains "de"/);
  assert.match(smoke, /languages\) -contains "en"/);
  assert.match(smoke, /api\/health/);
  assert.match(smoke, /Silent in-place upgrade failed/);
  assert.match(smoke, /In-place upgrade removed private customer data/);
  assert.match(smoke, /second\.WaitForExit\(15000\)/);
  assert.match(smoke, /Windows uninstall left private application data behind/);
});

test("release automation installs the hash-locked Python build", () => {
  const projectRoot = path.resolve(desktopRoot, "..");
  const workflow = fs.readFileSync(path.join(projectRoot, ".github", "workflows", "build-installers.yml"), "utf8");
  const lockfile = fs.readFileSync(path.join(projectRoot, "requirements-build.lock.txt"), "utf8");
  const backendLauncher = fs.readFileSync(path.join(desktopRoot, "scripts", "run_backend_build.cjs"), "utf8");
  const rootManifest = JSON.parse(fs.readFileSync(path.join(projectRoot, "package.json"), "utf8"));
  const pythonLauncher = fs.readFileSync(path.join(projectRoot, "scripts", "run_python.cjs"), "utf8");
  assert.match(workflow, /--require-hashes -r requirements-build\.lock\.txt/);
  assert.match(lockfile, /--hash=sha256:/);
  assert.match(lockfile, /pyinstaller==/);
  assert.match(backendLauncher, /import sys, PyInstaller/);
  assert.match(rootManifest.scripts["release:audit"], /^node scripts\/run_python\.cjs /);
  assert.match(rootManifest.scripts["release:checksums"], /^node scripts\/run_python\.cjs /);
  assert.match(pythonLauncher, /process\.platform === "win32"/);
  assert.match(pythonLauncher, /\["py", \["-3\.11"\]\]/);
  assert.match(pythonLauncher, /sys\.version_info >= \(3, 11\)/);
});
