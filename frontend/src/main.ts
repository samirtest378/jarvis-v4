/** JARVIS desktop/web client: voice, text chat, audio, and status UI. */

// Type-only: the live animations and their Three.js dependency are imported
// dynamically below, so the default (pre-rendered) path never loads them.
import type { Orb, OrbState } from "./orb";
import { createVoiceInput, createAudioPlayer, createBrowserSpeechPlayer } from "./voice";
import { canExtendVoiceConversation, isFatalVoiceInputError } from "./voice_activity.js";
import { createSocket } from "./ws";
import { isWakeFragment, parseWakeCommand } from "./wake.js";
import { openSettings, checkFirstTimeSetup } from "./settings";
import { tr, watchUiLanguage } from "./i18n";
import {
  apiUrl,
  authHeaders,
  getDesktopBridge,
  getRuntimeConfig,
  webSocketProtocols,
  voiceWebSocketUrl,
} from "./runtime";
import "./style.css";

watchUiLanguage();

type State = "idle" | "listening" | "thinking" | "speaking";
type MessageRole = "user" | "assistant" | "system";

let currentState: State = "idle";
let isMuted = true;
let voiceStarted = false;
let lastAssistantText = "";
// Off until the user explicitly enables it. Always-on recognition is the
// largest idle cost and an unexpected open microphone is a poor first-run
// experience. The main microphone button and Settings can enable it instantly.
let wakeEnabled = localStorage.getItem("jarvis_wake_enabled") === "1";
let speechLanguage = localStorage.getItem("jarvis_speech_language") || "auto";
let wakeFollowupUntil = 0;
let voiceConversationActive = false;
let voiceReplyPending = false;
let streamedVoicePending = false;
let wakeTest: { previousMuted: boolean; timer: number } | null = null;

const statusEl = document.getElementById("status-text")!;
const errorEl = document.getElementById("error-text")!;
const connectionEl = document.getElementById("connection-status")!;
const messagesEl = document.getElementById("messages")!;
const emptyStateEl = document.getElementById("empty-state")!;
const inputEl = document.getElementById("message-input") as HTMLTextAreaElement;
const sendButton = document.getElementById("btn-send") as HTMLButtonElement;
const btnMute = document.getElementById("btn-mute")!;
const welcomeTitle = document.getElementById("welcome-title");

const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;
const orbStage = document.getElementById("orb-stage");
let storedOrbStyle = localStorage.getItem("jarvis_orb_style");
// Versions 0.7.0–0.7.4 could silently persist the multi-video renderer while
// saving unrelated voice settings. Migrate that legacy value exactly once so
// existing installations receive the continuous animation too. Afterwards an
// intentional user choice of the recorded low-power mode remains respected.
const SMOOTH_ORB_MIGRATION = "jarvis_smooth_orb_migration_v1";
if (localStorage.getItem(SMOOTH_ORB_MIGRATION) !== "1") {
  if (storedOrbStyle === "video") {
    storedOrbStyle = "live";
    localStorage.setItem("jarvis_orb_style", "live");
  }
  localStorage.setItem(SMOOTH_ORB_MIGRATION, "1");
}
// The continuous live renderer is the product default. It owns one persistent
// particle scene and eases between states, so listening/thinking/speaking
// never swaps media and can never show a cut. Recorded clips remain available
// as an explicit low-power option.
const orbStyle = storedOrbStyle === "classic"
  ? "classic"
  : storedOrbStyle === "video"
    ? "video"
    : "live";

/** Play recorded clips of the real animation instead of simulating particles.
 *
 * The hardware video decoder replays them at a small fraction of the energy
 * the live scene needed, so the animation never has to freeze to stay cheap.
 * Only the clip for the current state plays; the others stay paused, which
 * costs nothing. The stylesheet cross-fades between them. */
function createVideoOrb(stage: HTMLElement): Orb {
  const clips = new Map<string, HTMLVideoElement>();
  const objectUrls: string[] = [];
  for (const clip of stage.querySelectorAll<HTMLVideoElement>(".orb-clip")) {
    const name = clip.dataset.state;
    if (!name) continue;
    clips.set(name, clip);
    // Only the resting clip should start by itself.
    if (name !== "idle") clip.pause();
  }

  let current: OrbState = "idle";

  const start = (clip: HTMLVideoElement | undefined, fromBeginning: boolean) => {
    if (!clip || document.hidden) return;
    if (fromBeginning) clip.currentTime = 0;
    void clip.play().catch(() => { /* a clip that will not start simply stays dark */ });
  };

  // Each non-idle clip opens on its real transition and then contains a
  // forwards/backwards settled section. At the end, return to the start of
  // that settled section rather than replaying the transition.
  for (const [state, clip] of clips) {
    const loopStart = Number(clip.dataset.loopStart || 0);
    if (loopStart <= 0) {
      clip.loop = true;
      continue;
    }
    clip.loop = false;
    clip.addEventListener("ended", () => {
      clip.currentTime = loopStart;
      if (current === state && !document.hidden) {
        void clip.play().catch(() => {});
      }
    });
  }

  const play = () => {
    if (document.hidden) return;
    start(clips.get(current), false);
  };

  // Hold the clip in memory instead of letting it stream.
  //
  // A looping <video> served over HTTP re-reads its source on every wrap, and
  // that read is visible as a stutter at the loop point. Fetching the file once
  // and playing it from an object URL removes the stall: after the first load
  // nothing touches the network or disk again.
  for (const clip of clips.values()) {
    const source = clip.getAttribute("src");
    if (!source) continue;
    void fetch(source)
      .then((response) => (response.ok ? response.blob() : Promise.reject(new Error("clip unavailable"))))
      .then((blob) => {
        const wasPlaying = !clip.paused;
        const resumeAt = clip.currentTime;
        const objectUrl = URL.createObjectURL(blob);
        objectUrls.push(objectUrl);
        clip.src = objectUrl;
        clip.currentTime = resumeAt;
        if (wasPlaying) void clip.play().catch(() => {});
      })
      .catch(() => { /* streaming from the original src still works */ });
  }

  const onVisibility = () => {
    // A decoder running behind a hidden window is pure waste.
    if (document.hidden) for (const clip of clips.values()) clip.pause();
    else play();
  };

  document.addEventListener("visibilitychange", onVisibility);
  play();

  return {
    setState(state) {
      if (state === current) return;
      const next = clips.get(state) ?? clips.get("idle");
      const previous = clips.get(current);
      current = state;
      document.body.dataset.orbState = state;
      // Play the new clip from its first frame so its transition is shown.
      start(next, true);
      // Pause the outgoing clip only once it has faded out.
      if (previous && previous !== next) {
        window.setTimeout(() => { if (clips.get(current) !== previous) previous.pause(); }, 380);
      }
    },
    setAnalyser() { /* a recording cannot react to live audio */ },
    setPowerSaving() { /* the recording's frame rate is already fixed */ },
    destroy() {
      document.removeEventListener("visibilitychange", onVisibility);
      for (const clip of clips.values()) clip.pause();
      for (const objectUrl of objectUrls) URL.revokeObjectURL(objectUrl);
    },
  };
}

// The live scene is the default. A user who explicitly selects the recorded
// low-power mode still gets the video implementation above.
const useVideoOrb = orbStyle === "video" && orbStage !== null;
if (!useVideoOrb) {
  orbStage?.remove();
  canvas.hidden = false;
}

/** Stand-in until a live animation module finishes loading. */
function createPendingOrb(): Orb {
  return { setState() {}, setAnalyser() {}, setPowerSaving() {}, destroy() {} };
}

let orb: Orb = useVideoOrb ? createVideoOrb(orbStage) : createPendingOrb();

if (!useVideoOrb) {
  // Three.js is roughly 490 KB of JavaScript to download, parse, and keep in
  // memory. The pre-rendered loop does not need it, so it is only fetched when
  // someone actually chooses a live animation.
  void (orbStyle === "classic" ? import("./orb.backup") : import("./orb"))
    .then((module) => {
      orb.destroy();
      orb = module.createOrb(canvas);
      orb.setState(currentState as OrbState);
      orb.setPowerSaving?.(powerSaving);
      const analyser = audioPlayer.getAnalyser?.();
      if (analyser) orb.setAnalyser(analyser);
    })
    .catch(() => showError("The live animation could not be loaded."));
}
const socket = createSocket(voiceWebSocketUrl(), webSocketProtocols());
const audioPlayer = createAudioPlayer();
const browserSpeech = createBrowserSpeechPlayer();
browserSpeech.setLanguage(speechLanguage);
// Keep the browser fallback aligned with JARVIS's configured language.  Wake
// acknowledgement itself is visual only; only real answers are ever spoken.
const persistedSettingsReady = fetch(apiUrl("/api/settings/status"), { headers: authHeaders() })
  .then((response) => (response.ok ? response.json() : null))
  .then((status) => {
    const configured = status?.tts?.system_voice_configured || status?.tts?.system_voice || "";
    if (configured) browserSpeech.setPreferredVoice(configured);
    if (status?.tts) {
      wakeEnabled = status.tts.wake_enabled === true;
      speechLanguage = status.tts.speech_language || speechLanguage;
      localStorage.setItem("jarvis_wake_enabled", wakeEnabled ? "1" : "0");
      localStorage.setItem("jarvis_speech_language", speechLanguage);
      browserSpeech.setLanguage(speechLanguage);
    }
  })
  .catch(() => { /* the language-based choice below is a fine fallback */ });

function persistWakeSetting(enabled: boolean) {
  void fetch(apiUrl("/api/settings/wake"), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ enabled }),
  }).catch(() => { /* local state still controls the current session */ });
}

// The audio graph is created on the first sound, so the orb receives its
// analyser then rather than holding an idle audio device open from startup.
audioPlayer.onAnalyser((analyser) => orb.setAnalyser(analyser));

// The live renderer holds a stable 60 Hz cadence. Power saving still pauses it
// behind hidden windows, but never lowers the visible motion frame rate.
const powerSaving = localStorage.getItem("jarvis_power_saving") !== "0";
orb.setPowerSaving?.(powerSaving);

// An unfocused window still animated at full rate behind other apps. Dropping
// the animation while JARVIS is not the active window costs nothing visually.
window.addEventListener("blur", () => orb.setPowerSaving?.(true));
window.addEventListener("focus", () => orb.setPowerSaving?.(powerSaving));

// Resting state. A single timeout — not an interval — marks the interface as
// resting after a few quiet seconds, which pauses the decorative CSS loops
// (see style.css). Those loops otherwise force the stacked backdrop-filter
// layers to recompute forever while nobody is using the app.
const REST_AFTER_MS = 6000;
let restTimer = 0;
function markActivity() {
  document.body.classList.remove("is-resting");
  window.clearTimeout(restTimer);
  restTimer = window.setTimeout(() => document.body.classList.add("is-resting"), REST_AFTER_MS);
}
for (const name of ["pointermove", "pointerdown", "keydown", "wheel", "focus"] as const) {
  window.addEventListener(name, markActivity, { passive: true });
}
markActivity();

function showError(message: string) {
  errorEl.textContent = message;
  errorEl.style.opacity = "1";
  window.setTimeout(() => {
    errorEl.style.opacity = "0";
  }, 6000);
}

function addMessage(role: MessageRole, text: string) {
  const normalized = text.trim();
  if (!normalized) return;
  emptyStateEl.hidden = true;
  const article = document.createElement("article");
  article.className = `message message-${role}`;
  const meta = document.createElement("div");
  meta.className = "message-meta";
  const label = document.createElement("span");
  label.className = "message-label";
  label.textContent = role === "assistant" ? "JARVIS v4" : role === "user" ? tr("YOU") : tr("SYSTEM");
  const time = document.createElement("time");
  const now = new Date();
  time.dateTime = now.toISOString();
  time.textContent = now.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  meta.append(label, time);
  if (role !== "system") {
    const copy = document.createElement("button");
    copy.type = "button";
    copy.className = "message-copy";
    copy.textContent = tr("Copy");
    copy.setAttribute("aria-label", `Copy ${role === "assistant" ? "JARVIS response" : "your message"}`);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(normalized);
        copy.textContent = tr("Copied");
        window.setTimeout(() => { copy.textContent = tr("Copy"); }, 1400);
      } catch {
        showError("The message could not be copied.");
      }
    });
    meta.append(copy);
  }
  const body = document.createElement("p");
  body.textContent = normalized;
  article.append(meta, body);
  messagesEl.appendChild(article);
  while (messagesEl.childElementCount > 30) {
    messagesEl.firstElementChild?.remove();
  }
  messagesEl.scrollTo({ top: messagesEl.scrollHeight, behavior: "smooth" });
}

function resizeComposerInput() {
  inputEl.style.height = "auto";
  inputEl.style.height = `${Math.min(inputEl.scrollHeight, 120)}px`;
  inputEl.style.overflowY = inputEl.scrollHeight > 120 ? "auto" : "hidden";
}

function showAssistantText(value: unknown) {
  const text = typeof value === "string" ? value.trim() : "";
  if (!text || text === lastAssistantText) return;
  lastAssistantText = text;
  addMessage("assistant", text);
}

function updateStatus(state: State) {
  const labels: Record<State, string> = {
    idle: tr(isMuted ? "Ready — type a message or enable the microphone" : wakeEnabled ? "Waiting for “Hey JARVIS”…" : "Ready"),
    listening: tr(wakeEnabled && Date.now() > wakeFollowupUntil ? "Waiting for “Hey JARVIS”…" : "Listening — just keep talking…"),
    thinking: tr("Thinking…"),
    speaking: tr("Speaking…"),
  };
  statusEl.textContent = labels[state];
}

function transition(newState: State) {
  currentState = newState;
  orb.setState(newState as OrbState);
  updateStatus(newState);
  // Thinking and speaking are real activity. "Listening" is not: with the wake
  // phrase enabled it is the permanent resting state, and treating it as
  // activity kept the decorative loops — and with them the whole glass stack —
  // awake around the clock.
  if (newState === "thinking" || newState === "speaking") markActivity();
  if (newState === "thinking" || newState === "speaking") {
    // In wake-phrase mode the microphone stays open through the reply, so the
    // next thing said is caught from its first word. Otherwise it is released.
    voiceInput.pause(wakeEnabled && !isMuted);
  } else if (!isMuted && voiceStarted) {
    voiceInput.resume();
  }
}

type UserInputContext = {
  inputMode?: "text" | "voice";
  wakeTriggered?: boolean;
};

function sendUserText(text: string, context: UserInputContext = {}) {
  const normalized = text.trim();
  if (!normalized) return;
  audioPlayer.stop();
  browserSpeech.stop();
  const sent = socket.send({
    type: "transcript",
    text: normalized,
    isFinal: true,
    input_mode: context.inputMode || "text",
    wake_triggered: context.wakeTriggered === true,
  });
  if (!sent) {
    showError("JARVIS v4 is still connecting. Please try again in a moment.");
    return;
  }
  if (context.inputMode === "voice" && context.wakeTriggered === true) {
    voiceConversationActive = true;
    voiceReplyPending = true;
  } else if (context.inputMode !== "voice") {
    // Typing is independent from hands-free mode. A typed turn must never make
    // ambient room speech count as a wake-authorized follow-up.
    voiceConversationActive = false;
    voiceReplyPending = false;
    wakeFollowupUntil = 0;
  }
  addMessage("user", normalized);
  transition("thinking");
}

function updateWelcomeMessage() {
  if (!welcomeTitle) return;
  const hour = new Date().getHours();
  const greeting = tr(hour < 5 ? "Still awake?" : hour < 12 ? "Good morning." : hour < 18 ? "Good afternoon." : "Good evening.");
  welcomeTitle.textContent = greeting;
}

document.querySelectorAll<HTMLButtonElement>(".quick-action").forEach((button) => {
  button.addEventListener("click", () => {
    const prompt = button.dataset.prompt || "";
    if (prompt) sendUserText(prompt);
  });
});

type WakeTestState = "listening" | "heard" | "success" | "timeout" | "unsupported" | "error";

function reportWakeTest(state: WakeTestState, text = "", error = "") {
  window.dispatchEvent(new CustomEvent("jarvis:wake-test-result", {
    detail: { state, text, error },
  }));
}

function finishWakeTest(state: Exclude<WakeTestState, "listening" | "heard">, text = "", error = "") {
  if (!wakeTest) return;
  const { previousMuted, timer } = wakeTest;
  wakeTest = null;
  window.clearTimeout(timer);
  reportWakeTest(state, text, error);

  const failed = state === "error" || state === "unsupported";
  if (failed) voiceStarted = false;
  isMuted = previousMuted || failed;
  btnMute.classList.toggle("muted", isMuted);
  btnMute.setAttribute("aria-pressed", String(!isMuted));
  if (isMuted) {
    voiceInput.stop();
    voiceStarted = false;
    transition("idle");
  } else {
    voiceInput.resume();
    transition("listening");
  }
}

/** How long JARVIS keeps answering without hearing the wake phrase again.
 *
 * A conversation is a back-and-forth, and saying "Hey JARVIS" before every
 * single sentence is not one. After the wake phrase — and again after each
 * reply — this window stays open so the next thing said is simply heard. */
const CONVERSATION_WINDOW_MS = 45000;

/** Reopen the window once JARVIS has finished speaking, so the natural thing
 *  to do — just answer back — works. */
function keepConversationOpen() {
  const now = Date.now();
  if (!canExtendVoiceConversation({
    wakeEnabled,
    isMuted,
    voiceConversationActive,
    voiceReplyPending,
    wakeFollowupUntil,
    now,
  })) {
    voiceConversationActive = false;
    voiceReplyPending = false;
    wakeFollowupUntil = 0;
    return;
  }
  voiceReplyPending = false;
  wakeFollowupUntil = now + CONVERSATION_WINDOW_MS;
}

function acknowledgeWake() {
  voiceConversationActive = true;
  voiceReplyPending = false;
  wakeFollowupUntil = Date.now() + CONVERSATION_WINDOW_MS;
  // A visual acknowledgement is immediate and cannot sound like a second,
  // unrelated assistant. The next actual answer always uses the selected
  // JARVIS voice.
  transition("listening");
  statusEl.textContent = "Listening — just keep talking…";
}

function handleVoiceTranscript(text: string): boolean {
  if (wakeTest) {
    const wake = parseWakeCommand(text);
    if (wake.matched) finishWakeTest("success", text);
    else reportWakeTest("heard", text);
    return wake.matched;
  }
  if (!wakeEnabled) {
    sendUserText(text, { inputMode: "voice" });
    return true;
  }
  if (Date.now() <= wakeFollowupUntil) {
    const repeatedWake = parseWakeCommand(text);
    if (repeatedWake.matched) {
      if (repeatedWake.command) {
        wakeFollowupUntil = 0;
        sendUserText(repeatedWake.command, { inputMode: "voice", wakeTriggered: true });
      } else {
        statusEl.textContent = "Yes — I’m listening…";
      }
      return true;
    }
    if (isWakeFragment(text)) {
      return false;
    }
    wakeFollowupUntil = 0;
    sendUserText(text, { inputMode: "voice", wakeTriggered: true });
    return true;
  }
  voiceConversationActive = false;
  voiceReplyPending = false;
  wakeFollowupUntil = 0;
  const wake = parseWakeCommand(text);
  if (!wake.matched) {
    updateStatus("listening");
    return false;
  }
  if (wake.command) sendUserText(wake.command, { inputMode: "voice", wakeTriggered: true });
  else acknowledgeWake();
  return true;
}

const voiceInput = createVoiceInput(handleVoiceTranscript, (message) => {
  if (wakeTest) {
    finishWakeTest("error", "", message);
    return;
  }
  if (isFatalVoiceInputError(message)) {
    voiceStarted = false;
    isMuted = true;
    btnMute.classList.add("muted");
    btnMute.setAttribute("aria-pressed", "false");
    voiceInput.stop();
    transition("idle");
    showError(`${message} You can continue by typing below.`);
    return;
  }
  // Local inference can fail for one noisy window or during a brief backend
  // restart. Keep the microphone session alive and recover automatically.
  isMuted = false;
  btnMute.classList.remove("muted");
  btnMute.setAttribute("aria-pressed", "true");
  voiceInput.resume();
  transition("listening");
  showError(`${message} Listening continues automatically.`);
});
voiceInput.setLanguage(speechLanguage);

window.addEventListener("jarvis:wake-test-start", ((event: CustomEvent<{ language?: string }>) => {
  if (!voiceInput.isSupported()) {
    reportWakeTest("unsupported", "", "Speech recognition is unavailable on this computer.");
    return;
  }
  if (wakeTest) finishWakeTest("timeout");
  const previousMuted = isMuted;
  const language = event.detail?.language || localStorage.getItem("jarvis_speech_language") || "auto";
  voiceInput.setLanguage(language);
  audioPlayer.stop();
  browserSpeech.stop();
  isMuted = false;
  btnMute.classList.remove("muted");
  btnMute.setAttribute("aria-pressed", "true");
  const timer = window.setTimeout(() => finishWakeTest("timeout"), 12000);
  wakeTest = { previousMuted, timer };
  reportWakeTest("listening");
  if (!voiceStarted) {
    voiceStarted = true;
    voiceInput.start();
  } else {
    voiceInput.resume();
  }
  transition("listening");
}) as EventListener);

function startWakeListening() {
  if (!wakeEnabled || voiceStarted || !voiceInput.isSupported()) return;
  isMuted = false;
  voiceStarted = true;
  btnMute.classList.remove("muted");
  btnMute.setAttribute("aria-pressed", "true");
  voiceInput.start();
  transition("listening");
}

window.addEventListener("jarvis:wake-setting", ((event: CustomEvent<{ enabled: boolean; language: string }>) => {
  wakeEnabled = event.detail.enabled;
  speechLanguage = event.detail.language || "auto";
  voiceInput.setLanguage(speechLanguage);
  browserSpeech.setLanguage(speechLanguage);
  if (wakeEnabled) startWakeListening();
  else {
    wakeFollowupUntil = 0;
    voiceConversationActive = false;
    voiceReplyPending = false;
    isMuted = true;
    voiceInput.stop();
    voiceStarted = false;
    btnMute.classList.add("muted");
    btnMute.setAttribute("aria-pressed", "false");
    transition("idle");
  }
}) as EventListener);

audioPlayer.onFinished(() => {
  if (streamedVoicePending) return;
  keepConversationOpen();
  transition("idle");
});

socket.onConnectionChange((connected) => {
  connectionEl.classList.toggle("online", connected);
  connectionEl.querySelector("span:last-child")!.textContent = tr(connected ? "Connected" : "Connecting…");
  sendButton.disabled = !connected;
  if (connected && currentState === "idle") updateStatus("idle");
});

socket.onMessage((message) => {
  const type = String(message.type || "");
  if (type === "audio") {
    showAssistantText(message.text);
    if (message.stream_final === false) streamedVoicePending = true;
    const data = typeof message.data === "string" ? message.data : "";
    const text = typeof message.text === "string" ? message.text.trim() : "";
    if (data) {
      browserSpeech.stop();
      transition("speaking");
      void audioPlayer.enqueue(data).then(() => {
        if (message.stream_final === true) streamedVoicePending = false;
      }).catch(() => {
        if (message.stream_final === true) streamedVoicePending = false;
        if (!text || !browserSpeech.isSupported()) {
          showError("The voice audio could not be played. The response is still available as text.");
          transition("idle");
          return;
        }
        void browserSpeech.speak(text)
          .then(() => { keepConversationOpen(); transition("idle"); })
          .catch((error) => {
            showError(error instanceof Error ? error.message : "Voice playback failed");
            keepConversationOpen();
            transition("idle");
          });
      });
    } else if (text && message.speak === true && browserSpeech.isSupported()) {
      if (message.stream_final === true) streamedVoicePending = false;
      transition("speaking");
      void browserSpeech.speak(text)
        .then(() => { keepConversationOpen(); transition("idle"); })
        .catch(() => { keepConversationOpen(); transition("idle"); });
    } else {
      if (message.stream_final === true) streamedVoicePending = false;
      transition("idle");
    }
  } else if (type === "text") {
    showAssistantText(message.text);
    const text = typeof message.text === "string" ? message.text.trim() : "";
    if (text && message.speak === true && browserSpeech.isSupported()) {
      transition("speaking");
      void browserSpeech.speak(text)
        .then(() => { keepConversationOpen(); transition("idle"); })
        .catch((error) => {
          showError(error instanceof Error ? error.message : "Voice playback failed");
          keepConversationOpen();
          transition("idle");
        });
    } else if (message.voice_pending === true) {
      // Keep the microphone paused until the matching audio message arrives.
      // Reopening it in the synthesis gap can capture room speech—or JARVIS's
      // own first word—as a new user turn.
      transition("thinking");
    } else {
      keepConversationOpen();
      transition("idle");
    }
  } else if (type === "status") {
    const state = String(message.state || "");
    if (state === "thinking") transition("thinking");
    if (state === "working") {
      transition("thinking");
      statusEl.textContent = tr("Working…");
    }
    if (state === "idle") transition("idle");
  } else if (type === "task_spawned") {
    addMessage("system", tr("Background task started."));
  } else if (type === "task_complete") {
    const summary = typeof message.summary === "string" ? message.summary : tr("Background task complete.");
    addMessage("system", summary);
  }
});

document.getElementById("composer")!.addEventListener("submit", (event) => {
  event.preventDefault();
  const text = inputEl.value;
  inputEl.value = "";
  resizeComposerInput();
  sendUserText(text);
  inputEl.focus();
});

inputEl.addEventListener("input", resizeComposerInput);
inputEl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
    event.preventDefault();
    inputEl.form?.requestSubmit();
  }
});

btnMute.classList.add("muted");
btnMute.setAttribute("aria-pressed", "false");
btnMute.addEventListener("click", (event) => {
  event.stopPropagation();
  if (!voiceInput.isSupported()) {
    showError("Speech recognition is unavailable here. Text chat remains fully available.");
    return;
  }
  isMuted = !isMuted;
  btnMute.classList.toggle("muted", isMuted);
  btnMute.setAttribute("aria-pressed", String(!isMuted));
  if (isMuted) {
    localStorage.setItem("jarvis_wake_enabled", "0");
    persistWakeSetting(false);
    wakeEnabled = false;
    wakeFollowupUntil = 0;
    voiceConversationActive = false;
    voiceReplyPending = false;
    voiceInput.pause();
    transition("idle");
  } else {
    localStorage.setItem("jarvis_wake_enabled", "1");
    persistWakeSetting(true);
    wakeEnabled = true;
    if (!voiceStarted) {
      voiceStarted = true;
      voiceInput.start();
    } else {
      voiceInput.resume();
    }
    transition("listening");
  }
});

const btnMenu = document.getElementById("btn-menu")!;
const menuDropdown = document.getElementById("menu-dropdown")!;
btnMenu.addEventListener("click", (event) => {
  event.stopPropagation();
  menuDropdown.hidden = !menuDropdown.hidden;
});
document.addEventListener("click", () => { menuDropdown.hidden = true; });

document.getElementById("btn-settings")!.addEventListener("click", (event) => {
  event.stopPropagation();
  menuDropdown.hidden = true;
  void openSettings();
});

getDesktopBridge()?.onOpenSettings(() => { void openSettings(); });
document.addEventListener("keydown", (event) => {
  if ((event.metaKey || event.ctrlKey) && event.key === ",") {
    event.preventDefault();
    void openSettings();
  }
});

document.getElementById("btn-restart")!.addEventListener("click", async (event) => {
  event.stopPropagation();
  menuDropdown.hidden = true;
  statusEl.textContent = "Restarting…";
  try {
    const desktop = getDesktopBridge();
    if (desktop) {
      const result = await desktop.restartBackend();
      if (!result.success) throw new Error(result.error || "Restart failed");
    } else {
      const response = await fetch(apiUrl("/api/restart"), {
        method: "POST",
        headers: authHeaders(),
      });
      if (!response.ok) throw new Error("Restart failed");
    }
  } catch (error) {
    showError(error instanceof Error ? error.message : "Restart failed");
  }
});

const workModeButton = document.getElementById("btn-fix-self")!;
if (!getRuntimeConfig().development) workModeButton.remove();
workModeButton.addEventListener("click", (event) => {
  event.stopPropagation();
  menuDropdown.hidden = true;
  if (!socket.send({ type: "fix_self" })) showError("JARVIS v4 is not connected yet.");
});

// One gesture is all the autoplay policy needs. Listening on every click kept
// waking the audio device again after the player had put it to sleep.
function ensureAudioContext() {
  audioPlayer.unlock();
}
document.addEventListener("click", ensureAudioContext, { once: true });
document.addEventListener("touchstart", ensureAudioContext, { once: true });
document.addEventListener("keydown", ensureAudioContext, { once: true });

updateStatus("idle");
updateWelcomeMessage();
inputEl.focus();
window.setTimeout(() => {
  void persistedSettingsReady.then(() => checkFirstTimeSetup()).then((setupOpened) => {
    if (!setupOpened) startWakeListening();
  });
}, 1200);
