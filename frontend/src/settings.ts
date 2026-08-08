/**
 * JARVIS v4 — Settings Panel
 *
 * Overlay panel for API keys, connection status, preferences, and system info.
 * Slides in from the right with glass-morphism styling.
 */

import { apiUrl, authHeaders, getDesktopBridge, getRuntimeConfig, type AccessState, type DiagnosticsReport, type SecretStorageStatus, type SystemAccessStatus } from "./runtime";
import { accessPresentation, summarizeCoreAccess } from "./access_status.js";
import { voiceLanguageStateText } from "./voice_language.js";
import { createBrowserSpeechPlayer } from "./voice";
import { getUiLanguage, setUiLanguage, translateDom } from "./i18n";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface StatusResponse {
  claude_code_installed: boolean;
  calendar_accessible: boolean;
  mail_accessible: boolean;
  notes_accessible: boolean;
  memory_count: number;
  task_count: number;
  server_port: number;
  uptime_seconds: number;
  llm_provider: LLMProvider;
  llm_base_url: string;
  llm_model: string;
  research_model: string;
  llm_configured: boolean;
  llm_ready: boolean;
  llm_readiness: {
    ready: boolean;
    runtime_installed: boolean;
    service_available: boolean;
    model_installed: boolean;
    installed_models: string[];
    error: string;
  };
  stt: {
    available: boolean;
    engine: "whisper.cpp" | "system-fallback";
    model: string;
    running: boolean;
    local: boolean;
    last_error: string;
    configured_provider: "auto" | "openai" | "fish" | "local" | "off";
    active_provider: "openai" | "fish" | "local" | "off";
    fallback_chain: string[];
    openai_ready: boolean;
    fish_ready: boolean;
    local_ready: boolean;
    local_running: boolean;
    local_memory_budget_mb: number;
    cloud: boolean;
  };
  capabilities: {
    platform: string;
    browser_and_apps: boolean;
    project_terminal: boolean;
    screen_capture: boolean;
    local_voice_input: boolean;
    local_ai_ready: boolean;
    private_calendar: boolean;
    private_mail: boolean;
    private_notes: boolean;
    google_account_connected: boolean;
  };
  tts: {
    configured_provider: "auto" | "openai" | "local" | "fish" | "system" | "off";
    active_provider: "openai" | "local" | "fish" | "system" | "unavailable";
    openai_ready: boolean;
    openai_model: string;
    openai_voice: string;
    local_ready: boolean;
    local_running: boolean;
    local_device: string;
    local_error: string;
    local_pack_name: string;
    local_pack_version: string;
    local_mode?: string;
    local_languages?: string[];
    voice_pack_choice?: string;
    bilingual_pack_installed?: boolean;
    fish_ready: boolean;
    fish_error: string;
    last_provider: "" | "openai" | "local" | "fish" | "system";
    reference_voice_id: string;
    system_available: boolean;
    system_engine: string;
    system_voice: string;
    system_voice_configured: string;
    speech_language: string;
    wake_enabled: boolean;
    system_rate: number;
  };
  env_keys_set: {
    openai: boolean;
    anthropic: boolean;
    moonshot: boolean;
    dashscope: boolean;
    gemini: boolean;
    xai: boolean;
    custom: boolean;
    fish_audio: boolean;
    fish_voice_id: boolean;
    google_account: boolean;
    user_name: string;
  };
}

type LLMProvider = "ollama" | "openai" | "anthropic" | "kimi" | "qwen" | "gemini" | "grok" | "custom";

const LLM_PRESETS: Record<LLMProvider, {
  label: string;
  baseUrl: string;
  model: string;
  researchModel: string;
  keyInput: string;
  keyUrl: string;
  note: string;
}> = {
  ollama: {
    label: "Local AI · Ollama",
    baseUrl: "http://127.0.0.1:11434/v1",
    model: "qwen3.5:9b",
    researchModel: "qwen3.5:27b",
    keyInput: "",
    keyUrl: "https://ollama.com/download",
    note: "Runs on this computer with no API key. Qwen 3.5 9B is the balanced default; larger installed models can be selected below.",
  },
  openai: {
    label: "OpenAI",
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-5.4-nano",
    researchModel: "gpt-5.4-nano",
    keyInput: "input-openai-key",
    keyUrl: "https://platform.openai.com/api-keys",
    note: "Official OpenAI API. GPT-5.4 Nano remains the selected model for normal conversation and research mode.",
  },
  anthropic: {
    label: "Anthropic",
    baseUrl: "",
    model: "claude-sonnet-5",
    researchModel: "claude-opus-4-8",
    keyInput: "input-anthropic-key",
    keyUrl: "https://console.anthropic.com/settings/keys",
    note: "Direct Anthropic Messages API.",
  },
  kimi: {
    label: "Kimi / Moonshot",
    baseUrl: "https://api.moonshot.ai/v1",
    model: "kimi-k2.6",
    researchModel: "kimi-k3",
    keyInput: "input-moonshot-key",
    keyUrl: "https://platform.kimi.ai/console/api-keys",
    note: "Global Kimi API. K2.6 keeps chat fast; K3 is used for explicit deep research.",
  },
  qwen: {
    label: "Qwen / DashScope",
    baseUrl: "https://dashscope-intl.aliyuncs.com/compatible-mode/v1",
    model: "qwen3.7-plus",
    researchModel: "qwen3.7-max",
    keyInput: "input-dashscope-key",
    keyUrl: "https://www.alibabacloud.com/help/en/model-studio/get-api-key",
    note: "Alibaba Cloud Model Studio, Singapore international endpoint. Regional URLs remain editable for matching regional keys.",
  },
  gemini: {
    label: "Google Gemini",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    model: "gemini-3.6-flash",
    researchModel: "gemini-3.1-pro-preview",
    keyInput: "input-gemini-key",
    keyUrl: "https://aistudio.google.com/apikey",
    note: "Google Gemini via the official OpenAI-compatible API. A stable fast model is preselected.",
  },
  grok: {
    label: "xAI Grok",
    baseUrl: "https://api.x.ai/v1",
    model: "grok-4.3",
    researchModel: "grok-4.3",
    keyInput: "input-xai-key",
    keyUrl: "https://console.x.ai/",
    note: "xAI Grok via its official OpenAI-compatible API.",
  },
  custom: {
    label: "Custom",
    baseUrl: "http://127.0.0.1:1234/v1",
    model: "local-model",
    researchModel: "local-model",
    keyInput: "input-custom-key",
    keyUrl: "",
    note: "Any OpenAI-compatible HTTPS endpoint, or a local HTTP endpoint on this computer.",
  },
};

interface PreferencesResponse {
  user_name: string;
  honorific: string;
  calendar_accounts: string;
}

interface TicketDashboardResponse {
  success: true;
  source: "pasted_snapshot" | "public_webpage";
  title: string;
  url: string;
  analyzed_at: string;
  language: "de" | "en";
  metrics: Record<"total" | "open" | "pending" | "urgent" | "new" | "closed", number | null>;
  summary: string;
  safety: {
    read_only: true;
    used_cookies: false;
    clicked_or_submitted: false;
    sent_to_ai_provider: false;
  };
}

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

let panelEl: HTMLElement | null = null;
let isOpen = false;
let isFirstTimeSetup = false;
let isPermissionOnlySetup = false;
let setupStep = 0; // 0=language model, 1=voice, 2=access, 3=name, 4=done
let activeSettingsPage = "section-api-keys";
let googleAccountConnected = false;
const browserSpeech = createBrowserSpeechPlayer();

const GMAIL_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 7v10" stroke="#4285F4" stroke-width="3"/><path d="M20.5 7v10" stroke="#34A853" stroke-width="3"/><path d="M3.5 7 12 13.3 20.5 7" fill="none" stroke="#EA4335" stroke-width="3" stroke-linejoin="round"/><path d="M3.5 17h4" stroke="#FBBC04" stroke-width="3"/></svg>`;
const GOOGLE_CALENDAR_ICON = `<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="#fff" d="M4 3h16v18H4z"/><path fill="#4285F4" d="M4 8h16v13H4z"/><path fill="#34A853" d="M4 8h5v5H4z"/><path fill="#FBBC04" d="M15 8h5v5h-5z"/><path fill="#EA4335" d="M15 3h5v5h-5z"/><text x="12" y="18" text-anchor="middle" fill="#fff" font-size="8" font-family="Arial" font-weight="700">31</text></svg>`;

const SETTINGS_PAGES: Record<string, string[]> = {
  "section-api-keys": ["section-api-keys"],
  "section-voice": ["section-voice"],
  "section-access": ["section-access"],
  "section-tickets": ["section-tickets"],
  "section-preferences": ["section-preferences"],
  "section-status": ["section-status", "section-sysinfo", "section-privacy-reset"],
};

function platformPresentation() {
  const platform = getRuntimeConfig().platform;
  if (platform === "darwin") {
    return {
      mac: true,
      systemName: "macOS",
      storageName: "macOS Keychain",
      storageOption: "macOS Keychain — most secure",
      privacyButton: "macOS Privacy Settings",
      accessHelp: "JARVIS asks only when you use a feature. This check shows actual macOS permissions rather than merely detecting installed apps.",
      permissionPrompt: "Checking permissions… macOS may ask for approval.",
      accessIntro: "One tap each. Mail and Calendar read the accounts already configured in the Mac apps.",
      nativeMail: "Apple Mail",
      nativeCalendar: "Apple Calendar",
      nativeMailDetail: "Gmail, iCloud, Exchange — every account in Mail",
      nativeCalendarDetail: "Every calendar in the Calendar app",
      appsLabel: "Spotify, Music, Safari & more",
      appsDetail: "Just say “open Spotify”",
    };
  }
  if (platform === "win32") {
    return {
      mac: false,
      systemName: "Windows",
      storageName: "Windows encryption",
      storageOption: "Windows encryption — recommended",
      privacyButton: "Windows Privacy Settings",
      accessHelp: "JARVIS uses Windows privacy controls for microphone and files. Classic Outlook provides private mail and calendar access locally when installed.",
      permissionPrompt: "Checking permissions… Windows may ask for approval.",
      accessIntro: "Classic Outlook mail and calendar work locally with the accounts already configured on this PC. Google remains available as an alternative.",
      nativeMail: "Outlook Mail",
      nativeCalendar: "Outlook Calendar",
      nativeMailDetail: "Reads and sends through configured classic Outlook",
      nativeCalendarDetail: "Reads today's events from classic Outlook",
      appsLabel: "Spotify, Chrome & more",
      appsDetail: "Say “open Chrome” or “open Spotify”",
    };
  }
  return {
    mac: false,
    systemName: "Linux",
    storageName: "system keyring",
    storageOption: "System keyring — recommended",
    privacyButton: "System Privacy Settings",
    accessHelp: "JARVIS uses your operating system's privacy controls. Private local JARVIS notes work here; connect Google for mail and calendar.",
    permissionPrompt: "Checking operating-system permissions…",
    accessIntro: "Connect Google for private mail and calendar access on this computer.",
    nativeMail: "Mail",
    nativeCalendar: "Calendar",
    nativeMailDetail: "Native mail bridge unavailable",
    nativeCalendarDetail: "Native calendar bridge unavailable",
    appsLabel: "Spotify, browser & more",
    appsDetail: "Say “open Spotify” or “open browser”",
  };
}

function configurePlatformPresentation() {
  const presentation = platformPresentation();
  document.querySelectorAll<HTMLElement>("[data-macos-only]").forEach((element) => {
    element.hidden = !presentation.mac;
  });
  const nativeOffice = getRuntimeConfig().platform === "darwin" || getRuntimeConfig().platform === "win32";
  document.querySelectorAll<HTMLElement>("[data-native-office]").forEach((element) => {
    element.hidden = !nativeOffice;
  });
  const text = (id: string, value: string) => {
    const element = document.getElementById(id);
    if (element) element.textContent = value;
  };
  text("access-intro", presentation.accessIntro);
  text("status-native-mail-label", presentation.nativeMail);
  text("status-native-calendar-label", presentation.nativeCalendar);
  text("connection-mail-label", presentation.nativeMail);
  text("connection-calendar-label", presentation.nativeCalendar);
  text("connection-mail-detail", presentation.nativeMailDetail);
  text("connection-calendar-detail", presentation.nativeCalendarDetail);
  text("connection-apps-label", presentation.appsLabel);
  text("connection-apps-detail", presentation.appsDetail);
  document.querySelectorAll<HTMLElement>("[data-native-office-manage]").forEach((element) => {
    element.hidden = !presentation.mac;
  });
  const secureOption = document.querySelector<HTMLOptionElement>("#input-key-storage option[value='keychain']");
  if (secureOption) secureOption.textContent = presentation.storageOption;
  const privacyButton = document.getElementById("btn-open-privacy");
  if (privacyButton) privacyButton.textContent = presentation.privacyButton;
  const accessHelp = document.getElementById("access-platform-help");
  if (accessHelp) accessHelp.textContent = presentation.accessHelp;
}

// ---------------------------------------------------------------------------
// API helpers
// ---------------------------------------------------------------------------

async function apiGet<T>(url: string): Promise<T> {
  const res = await fetch(apiUrl(url), { headers: authHeaders() });
  const payload = await res.json().catch(() => null) as (T & { error?: string }) | null;
  if (!res.ok) throw new Error(payload?.error || `Request failed (${res.status})`);
  if (payload === null) throw new Error("The assistant returned an empty response");
  return payload;
}

async function apiPost<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(apiUrl(url), {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  });
  const payload = await res.json().catch(() => null) as (T & { error?: string }) | null;
  if (!res.ok) throw new Error(payload?.error || `Request failed (${res.status})`);
  if (payload === null) throw new Error("The assistant returned an empty response");
  return payload;
}

function setFeedback(message: string, isError = false) {
  const feedback = document.getElementById("settings-feedback");
  if (!feedback) return;
  feedback.textContent = message;
  feedback.style.color = isError ? "rgba(248, 113, 113, 0.85)" : "rgba(125, 211, 252, 0.7)";
}

function setSectionFeedback(id: string, message: string, isError = false) {
  const feedback = document.getElementById(id);
  if (!feedback) return;
  feedback.textContent = message;
  feedback.style.color = isError ? "rgba(248, 113, 113, 0.85)" : "rgba(125, 211, 252, 0.7)";
}

async function waitForBackend() {
  for (let attempt = 0; attempt < 20; attempt++) {
    try {
      const response = await fetch(apiUrl("/api/health"));
      if (response.ok) return;
    } catch {
      // Backend is still restarting.
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error("The assistant did not restart in time");
}

// ---------------------------------------------------------------------------
// Panel HTML
// ---------------------------------------------------------------------------

function buildPanelHTML(): string {
  return `
    <div class="settings-backdrop" id="settings-backdrop"></div>
    <div class="settings-panel" id="settings-panel-inner">
      <div class="settings-header">
        <div class="settings-title-group">
          <span class="settings-eyebrow">JARVIS v4</span>
          <h2>Settings</h2>
        </div>
        <button class="settings-close" id="settings-close" aria-label="Close settings">&times;</button>
      </div>

      <div class="settings-welcome" id="settings-welcome" style="display:none">
        <strong id="setup-progress">Step 1 of 4</strong>
        <p id="setup-copy">Choose the intelligence JARVIS should use. You can change this later.</p>
      </div>

      <nav class="settings-nav" id="settings-section-nav" aria-label="Settings sections" role="tablist">
        <button class="settings-nav-button active" type="button" role="tab" aria-selected="true" data-settings-target="section-api-keys">AI</button>
        <button class="settings-nav-button" type="button" role="tab" aria-selected="false" data-settings-target="section-voice">Voice</button>
        <button class="settings-nav-button" type="button" role="tab" aria-selected="false" data-settings-target="section-access">Access</button>
        <button class="settings-nav-button" type="button" role="tab" aria-selected="false" data-settings-target="section-tickets">Tickets</button>
        <button class="settings-nav-button" type="button" role="tab" aria-selected="false" data-settings-target="section-preferences">You</button>
        <button class="settings-nav-button" type="button" role="tab" aria-selected="false" data-settings-target="section-status">System</button>
      </nav>

      <div class="settings-body">

        <!-- Language model -->
        <section class="settings-section" id="section-api-keys">
          <h3>Intelligence</h3>
          <p class="settings-help" id="key-storage-help">Choose who powers JARVIS. The recommended settings are filled in for you.</p>

          <details class="settings-advanced">
            <summary>Security &amp; key storage</summary>
          <div class="settings-field settings-advanced-inline" id="desktop-storage-field">
            <label for="input-key-storage">Key storage</label>
            <select id="input-key-storage">
              <option value="local">Local file — no OS password</option>
              <option value="keychain">System encryption — most secure</option>
            </select>
            <p class="settings-help compact" id="key-storage-detail">Local storage avoids operating-system security prompts but is not encrypted.</p>
            <button class="settings-btn compact" id="btn-use-inactive-storage" type="button" hidden></button>
          </div>
          </details>

          <div class="settings-field">
            <label for="input-llm-provider">Provider</label>
            <select id="input-llm-provider">
              <option value="openai">OpenAI / ChatGPT API</option>
              <option value="anthropic">Anthropic</option>
              <option value="kimi">Kimi / Moonshot (Global)</option>
              <option value="qwen">Qwen / DashScope (International)</option>
              <option value="gemini">Google Gemini</option>
              <option value="grok">xAI Grok</option>
              <option value="custom">Custom OpenAI-compatible</option>
            </select>
            <p class="settings-help compact" id="llm-provider-note"></p>
            <a class="provider-dashboard-link" id="llm-provider-key-link" target="_blank" rel="noreferrer"></a>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="openai" hidden>
            <label>OpenAI API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-openai-key" autocomplete="off" placeholder="sk-…" />
              <span class="status-dot" id="status-openai"></span>
            </div>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="anthropic">
            <label>Anthropic API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-anthropic-key" autocomplete="off" placeholder="sk-ant-…" />
              <span class="status-dot" id="status-anthropic"></span>
            </div>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="kimi" hidden>
            <label>Moonshot API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-moonshot-key" autocomplete="off" placeholder="Moonshot key…" />
              <span class="status-dot" id="status-moonshot"></span>
            </div>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="qwen" hidden>
            <label>DashScope API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-dashscope-key" autocomplete="off" placeholder="sk-…" />
              <span class="status-dot" id="status-dashscope"></span>
            </div>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="gemini" hidden>
            <label>Gemini API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-gemini-key" autocomplete="off" placeholder="Google AI Studio key…" />
              <span class="status-dot" id="status-gemini"></span>
            </div>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="grok" hidden>
            <label>xAI API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-xai-key" autocomplete="off" placeholder="xai-…" />
              <span class="status-dot" id="status-xai"></span>
            </div>
          </div>

          <div class="settings-field provider-key-field" data-provider-key="custom" hidden>
            <label>Endpoint API Key <span class="label-optional">optional for local servers</span></label>
            <div class="settings-input-row">
              <input type="password" id="input-custom-key" autocomplete="off" placeholder="Optional bearer token…" />
              <span class="status-dot" id="status-custom"></span>
            </div>
          </div>

          <details class="settings-advanced">
            <summary>Model settings</summary>

          <div class="settings-field" id="llm-base-url-field" hidden>
            <label for="input-llm-base-url">Base URL</label>
            <input type="text" id="input-llm-base-url" spellcheck="false" placeholder="https://provider.example/v1" />
          </div>

          <div class="local-model-card" id="local-model-actions" hidden>
            <span class="status-dot" id="status-ollama"></span>
            <div>
              <strong>Private local intelligence</strong>
              <p id="local-model-status">Install and start Ollama, then detect the models already on this computer.</p>
            </div>
            <div class="local-model-buttons">
              <button class="settings-btn" id="btn-start-local-runtime" type="button" hidden>Start local AI</button>
              <button class="settings-btn" id="btn-detect-local-models" type="button">Detect models</button>
              <button class="settings-btn primary" id="btn-install-local-model" type="button">Install Qwen 3.5 9B · 6.6 GB</button>
            </div>
            <a href="https://ollama.com/download" target="_blank" rel="noreferrer">Get Ollama</a>
          </div>

          <div class="settings-field">
            <label for="input-llm-model">Chat model</label>
            <input type="text" id="input-llm-model" spellcheck="false" />
          </div>

          <div class="settings-field">
            <label for="input-research-model">Research model</label>
            <input type="text" id="input-research-model" spellcheck="false" />
          </div>
          </details>

          <div class="settings-actions">
            <button class="settings-btn" id="btn-test-llm">Test provider</button>
            <button class="settings-btn primary" id="btn-save-llm">Save & restart</button>
          </div>
          <div class="settings-feedback" id="settings-feedback" role="status"></div>
        </section>

        <!-- Voice and visualization -->
        <section class="settings-section" id="section-voice">
          <h3>Voice</h3>
          <p class="settings-help">JARVIS automatically understands German and English. Pick a voice and you are done.</p>

          <div class="voice-health-card" id="voice-health-card">
            <span>Active output</span>
            <strong id="voice-active-state">Checking…</strong>
          </div>

          <details class="settings-advanced">
            <summary>Fish Audio account</summary>
          <div class="settings-field">
            <label>Fish Audio API Key</label>
            <div class="settings-input-row">
              <input type="password" id="input-fish-key" autocomplete="off" placeholder="Fish Audio key…" />
              <button class="settings-btn" id="btn-test-fish">Test</button>
              <span class="status-dot" id="status-fish"></span>
            </div>
            <p class="settings-help compact">Speech needs a separate Fish key; a language-model key cannot power the voice. <a href="https://fish.audio/app/api-keys/" target="_blank" rel="noreferrer">Get a Fish key</a></p>
          </div>

          <div class="settings-field">
            <label>Fish Voice ID</label>
            <div class="settings-input-row">
              <input type="text" id="input-fish-voice-id" placeholder="Your licensed Fish voice ID" />
              <button class="settings-btn" id="btn-save-fish">Save Fish</button>
            </div>
            <p class="settings-help compact">Use a Fish voice you created or have permission to use commercially. No third-party celebrity or character voice is bundled.</p>
          </div>

          </details>

          <div class="settings-field">
            <label>Voice</label>
            <select id="input-voice-provider">
              <option value="system">Local system voice (recommended)</option>
              <option value="auto">Automatic fallback chain</option>
              <option value="local">Smooth JARVIS voice — German &amp; English</option>
              <option value="fish">Video reference — Fish Audio</option>
              <option value="off">Text only</option>
            </select>
            <p class="settings-help compact">The V4 voice uses separate V2-matched English and German profiles with a compact local NeuTTS engine. It warms in the background and stays ready for 30 quiet minutes, so later replies do not pay another cold start. The system voice remains the instant fallback.</p>
          </div>

          <details class="settings-advanced">
            <summary>Recognition engine</summary>
          <div class="settings-field">
            <label for="input-stt-provider">Recognition</label>
            <select id="input-stt-provider">
              <option value="local">On this computer — bundled Whisper (recommended)</option>
              <option value="auto">Automatic fallback chain</option>
              <option value="openai">Cloud — OpenAI</option>
              <option value="fish">Cloud — Fish Audio</option>
              <option value="off">Off — no dictation</option>
            </select>
            <p class="settings-help compact">Whisper Large-v3 Turbo Q8 recognizes German and English locally with high-precision weights and low-latency decoding. It keeps substantially more detail than the old Q5 pack, warms during startup and stays ready.</p>
          </div>
          </details>

          <div class="settings-field">
            <label for="input-wake-mode">“Hey JARVIS” on startup</label>
            <select id="input-wake-mode">
              <option value="off">Off — microphone starts only when you press the button (recommended)</option>
              <option value="on">On — answer whenever you say “Hey JARVIS”</option>
            </select>
            <p class="settings-help compact" id="speech-recognition-help">The microphone indicator is always visible. Speech is processed locally by bundled Whisper and can be disabled instantly from the main screen.</p>
            <span class="voice-pack-state" id="speech-engine-state">Checking speech engine…</span>
          </div>

          <div class="settings-field">
            <label for="input-speech-language">Language — Sprache</label>
            <select id="input-speech-language">
              <option value="auto">Automatic — German &amp; English (recommended)</option>
              <option value="de-DE">Deutsch — nur Deutsch</option>
              <option value="en-US">English (US) only</option>
              <option value="en-GB">English (UK) only</option>
            </select>
            <p class="settings-help compact">Sets what JARVIS listens for and which JARVIS voice answers. Automatic detects the language of each sentence, so you can switch between German and English mid-conversation without changing anything.</p>
            <span class="voice-pack-state" id="voice-language-state">Checking the JARVIS voice…</span>
          </div>

          <div class="wake-test-card" id="wake-test-card" data-state="idle">
            <div class="wake-test-indicator" aria-hidden="true"><span></span></div>
            <div class="wake-test-copy" aria-live="polite">
              <strong id="wake-test-state">Voice conversation not tested</strong>
              <span id="wake-test-detail">Run the check, then say “Hey JARVIS”. JARVIS will recognize you locally and play a reply. Fish may use one paid sample when selected.</span>
            </div>
            <button class="settings-btn" id="btn-test-wake" type="button">Run voice check</button>
          </div>

          <div class="voice-command-guide" aria-label="Voice command examples">
            <div class="voice-command-heading">
              <div><strong>Speak naturally</strong><span>Start with “Hey JARVIS”, then continue in German or English.</span></div>
              <span class="connection-badge is-ready">LOCAL</span>
            </div>
            <div class="voice-command-grid">
              <div><span>APP</span><strong>„Öffne Spotify.“</strong></div>
              <div><span>FILES</span><strong>„Zeige Downloads.“</strong></div>
              <div><span>DAY</span><strong>„Was steht heute an?“</strong></div>
              <div><span>SCREEN</span><strong>„Was ist auf meinem Bildschirm?“</strong></div>
            </div>
            <p>Private Gmail and Calendar answers require the verified Google connection. Opening their websites alone does not grant access.</p>
          </div>

          <details class="settings-advanced">
            <summary>Voice pack and fine-tuning</summary>
          <div class="voice-pack-card">
            <div>
              <strong>JARVIS v4 Smooth German &amp; English Voice</strong>
              <span class="voice-pack-state" id="voice-pack-state">Checking…</span>
            </div>
            <p>Runs only on this computer. Separate V2-matched English and German profiles keep the character consistent; German pronunciation and long artificial pauses are corrected automatically. On Windows, compatible NVIDIA GPUs use CUDA automatically; other PCs fall back safely to the CPU.</p>
            <button class="settings-btn" id="btn-install-voice-pack">Activate Existing Voice Pack…</button>
          </div>

          <div class="settings-field">
            <label>Local voice</label>
            <div class="settings-input-row">
              <input type="text" id="input-system-voice" value="Auto" placeholder="Auto" />
              <input type="number" id="input-system-rate" value="165" min="90" max="260" aria-label="Speech rate" />
            </div>
          </div>
          </details>

          <div class="settings-field">
            <label>Orb animation</label>
            <select id="input-orb-style">
              <option value="live">Smooth Live — continuous and audio-reactive (recommended)</option>
              <option value="video">Recorded 4K — low power</option>
              <option value="classic">Classic Backup — particles</option>
            </select>
            <p class="settings-help">Smooth Live keeps one uninterrupted scene running and blends naturally between every JARVIS state without video cuts.</p>
          </div>

          <div class="settings-actions">
            <button class="settings-btn" id="btn-test-voice">Test Voice</button>
            <button class="settings-btn primary" id="btn-save-voice">Save</button>
          </div>
          <div class="settings-feedback" id="voice-feedback" role="status"></div>
        </section>

        <!-- Connection Status -->
        <section class="settings-section" id="section-status">
          <div class="system-heading">
            <div>
              <h3>System Health</h3>
              <p class="settings-help">A clear, privacy-safe overview of this JARVIS installation.</p>
            </div>
            <span class="system-health-chip" id="system-health-chip">Checking…</span>
          </div>
          <div class="health-grid">
            <div class="health-card">
              <span>Local service</span>
              <strong id="health-service">Checking…</strong>
              <small>Runs on this computer</small>
            </div>
            <div class="health-card">
              <span>Intelligence</span>
              <strong id="health-intelligence">Checking…</strong>
              <small id="health-intelligence-detail">Provider status</small>
            </div>
            <div class="health-card">
              <span>Voice</span>
              <strong id="health-voice">Checking…</strong>
              <small>Active speech output</small>
            </div>
            <div class="health-card health-card-private">
              <span>Diagnostics privacy</span>
              <strong>Secret-free</strong>
              <small>No keys, chats or file paths</small>
            </div>
          </div>
          <div class="system-facts">
            <div><span>App version</span><strong id="system-app-version">${getRuntimeConfig().appVersion || "Web preview"}</strong></div>
            <div><span>Platform</span><strong id="system-platform">${getRuntimeConfig().platform}</strong></div>
            <div><span>Key protection</span><strong id="system-key-protection">Checking…</strong></div>
          </div>
          <h4 class="settings-subheading">Connections</h4>
          <div class="status-grid">
            <div class="status-row"><span class="status-dot" id="status-claude-cli"></span><span>Claude Code CLI</span></div>
            <div class="status-row" data-native-office><span class="status-dot" id="status-calendar"></span><span id="status-native-calendar-label">Calendar</span></div>
            <div class="status-row" data-native-office><span class="status-dot" id="status-mail"></span><span id="status-native-mail-label">Mail</span></div>
            <div class="status-row" data-macos-only><span class="status-dot" id="status-notes"></span><span>Apple Notes</span></div>
            <div class="status-row"><span class="status-dot" id="status-server"></span><span>Server</span><span class="status-detail" id="status-server-detail"></span></div>
          </div>
          <h4 class="settings-subheading">Available on this computer</h4>
          <div class="status-grid">
            <div class="status-row"><span class="status-dot" id="status-browser-apps"></span><span>Open websites, apps & folders</span><span class="status-detail" id="status-browser-apps-detail"></span></div>
            <div class="status-row"><span class="status-dot" id="status-local-listening"></span><span>Offline listening</span><span class="status-detail" id="status-local-listening-detail"></span></div>
            <div class="status-row"><span class="status-dot" id="status-screen-capture"></span><span>Screen understanding</span><span class="status-detail" id="status-screen-capture-detail"></span></div>
            <div class="status-row"><span class="status-dot" id="status-private-notes"></span><span>Private JARVIS notes</span><span class="status-detail" id="status-private-notes-detail"></span></div>
            <div class="status-row"><span class="status-dot" id="status-google-account"></span><span>Private Google account data</span><span class="status-detail" id="status-google-account-detail"></span></div>
          </div>
          <div class="settings-actions">
            <button class="settings-btn" id="btn-refresh-system">Refresh status</button>
            <button class="settings-btn" id="btn-test-connections">Test connections</button>
            <button class="settings-btn primary" id="btn-export-diagnostics">Export safe diagnostics…</button>
          </div>
          <p class="settings-help compact">Connection tests send only a tiny fixed test phrase to your selected providers. The diagnostic report contains no keys, chats, memories, personal file paths, or your name.</p>
          <div class="settings-feedback" id="support-feedback" role="status"></div>
        </section>

        <!-- Real operating-system permissions -->
        <section class="settings-section" id="section-access">
          <h3>Connections</h3>
          <p class="settings-help" id="access-intro">Mail and Calendar use the accounts already configured on this computer.</p>
          <div class="connection-list" id="connection-list">
            <div class="connection-row" data-connection="mail" data-native-office>
              <span class="connection-logo" data-logo="gmail" aria-hidden="true">✉</span>
              <span class="connection-text">
                <strong id="connection-mail-label">Email</strong>
                <small id="connection-mail-detail">Configured mail accounts</small>
              </span>
              <span class="connection-state" id="conn-mail-state">Checking…</span>
              <span class="connection-dot" id="conn-mail-dot"></span>
              <button class="connection-link" type="button" data-access-kind="automation" data-native-office-manage>Allow</button>
            </div>
            <div class="connection-row" data-connection="calendar" data-native-office>
              <span class="connection-logo" data-logo="gcal" aria-hidden="true">◷</span>
              <span class="connection-text">
                <strong id="connection-calendar-label">Calendar</strong>
                <small id="connection-calendar-detail">Configured calendars</small>
              </span>
              <span class="connection-state" id="conn-calendar-state">Checking…</span>
              <span class="connection-dot" id="conn-calendar-dot"></span>
              <button class="connection-link" type="button" data-access-kind="automation" data-native-office-manage>Allow</button>
            </div>
            <div class="connection-row" data-connection="notes" data-macos-only>
              <span class="connection-logo" data-logo="notes" aria-hidden="true">✎</span>
              <span class="connection-text">
                <strong>Apple Notes</strong>
                <small>Read and create notes</small>
              </span>
              <span class="connection-state" id="conn-notes-state">Checking…</span>
              <span class="connection-dot" id="conn-notes-dot"></span>
              <button class="connection-link" type="button" data-access-kind="automation">Allow</button>
            </div>
            <div class="connection-row" data-connection="files">
              <span class="connection-logo" data-logo="files" aria-hidden="true">◧</span>
              <span class="connection-text">
                <strong>Files</strong>
                <small>Desktop, Documents and Downloads</small>
              </span>
              <span class="connection-state" id="conn-files-state">Checking…</span>
              <span class="connection-dot" id="conn-files-dot"></span>
              <button class="connection-link" type="button" data-access-kind="files">Allow</button>
            </div>
            <div class="connection-row" data-connection="microphone">
              <span class="connection-logo" data-logo="mic" aria-hidden="true">◉</span>
              <span class="connection-text">
                <strong>Microphone</strong>
                <small>Needed for “Hey JARVIS”</small>
              </span>
              <span class="connection-state" id="conn-microphone-state">Checking…</span>
              <span class="connection-dot" id="conn-microphone-dot"></span>
              <button class="connection-link" type="button" data-access-kind="microphone">Allow</button>
            </div>
            <!-- Apps JARVIS launches. These need no sign-in: it opens them the
                 way you would from the Dock, so there is nothing to connect. -->
            <div class="connection-row" data-connection="apps">
              <span class="connection-logo" data-logo="spotify" aria-hidden="true">♪</span>
              <span class="connection-text">
                <strong id="connection-apps-label">Spotify, Music, Safari &amp; more</strong>
                <small id="connection-apps-detail">Just say “open Spotify”</small>
              </span>
              <span class="connection-state">Ready</span>
              <span class="connection-dot is-ready" id="conn-apps-dot"></span>
              <span class="connection-link is-static">No sign-in</span>
            </div>
          </div>

          <h4 class="settings-subheading google-connections-heading">Google Workspace</h4>
          <p class="settings-help compact google-connections-help">Select Gmail or Google Calendar to open Google’s secure approval page. JARVIS receives access only after you approve it.</p>
            <div class="connection-list google-service-list">
              <div class="connection-row connection-row-action" data-connection="google" data-google-connect role="button" tabindex="0" aria-label="Connect Gmail">
                <span class="connection-logo connection-logo-brand" data-logo="gmail" aria-hidden="true">${GMAIL_ICON}</span>
                <span class="connection-text">
                  <strong>Gmail via Google account</strong>
                  <small>Unread senders/subjects and instructed sending</small>
                </span>
                <span class="connection-state" id="conn-google-state">Checking…</span>
                <span class="connection-dot" id="conn-google-dot"></span>
                <button class="connection-link" type="button">Connect</button>
              </div>
              <div class="connection-row connection-row-action" data-connection="google-calendar" data-google-connect role="button" tabindex="0" aria-label="Connect Google Calendar">
                <span class="connection-logo connection-logo-brand" data-logo="gcal" aria-hidden="true">${GOOGLE_CALENDAR_ICON}</span>
                <span class="connection-text">
                  <strong>Google Calendar via Google account</strong>
                  <small>Read-only: upcoming events</small>
                </span>
                <span class="connection-state" id="conn-gcal-state">Checking…</span>
                <span class="connection-dot" id="conn-gcal-dot"></span>
                <button class="connection-link" type="button">Connect</button>
              </div>
            </div>

          <div class="google-account-card" id="google-account-card">
            <div class="google-account-heading">
              <div>
                <strong id="google-account-state">Not connected</strong>
                <p>Gmail metadata/sending and read-only Calendar access are enabled only after Google approval.</p>
              </div>
              <span class="connection-badge" id="google-account-badge">OFF</span>
            </div>
            <details class="settings-advanced google-app-setup" id="google-oauth-fields">
              <summary>App setup · seller only</summary>
              <p class="settings-help compact">A commercial build needs its verified Google Desktop OAuth client once. Customers should not normally see this step.</p>
              <ol class="google-steps">
                <li>Open Google Cloud and select the production project.</li>
                <li>Enable the <strong>Gmail API</strong> and <strong>Google Calendar API</strong>.</li>
                <li>Create a <strong>Desktop app</strong> OAuth client.</li>
                <li>Paste its client ID, then select Connect.</li>
              </ol>
              <div class="settings-actions">
                <button class="settings-btn" id="btn-open-google-console" type="button">Open Google Cloud console…</button>
              </div>
              <div class="settings-field">
                <label for="input-google-client-id">Client ID</label>
                <input type="text" id="input-google-client-id" autocomplete="off" placeholder="…apps.googleusercontent.com" />
              </div>
              <div class="settings-field">
                <label for="input-google-client-secret">Client secret <span class="label-optional">only if Google gave you one</span></label>
                <input type="password" id="input-google-client-secret" autocomplete="new-password" placeholder="Optional" />
              </div>
            </details>
            <div class="settings-actions">
              <button class="settings-btn primary" id="btn-connect-google">Connect Google…</button>
              <button class="settings-btn danger" id="btn-disconnect-google" hidden>Disconnect</button>
            </div>
            <p class="settings-help compact">JARVIS never edits or deletes existing mail or calendar events. The account token stays in protected Windows storage and can be revoked here.</p>
            <div class="settings-feedback" id="google-feedback" role="status"></div>
          </div>

          <details class="settings-advanced">
            <summary>Technical detail — raw permissions</summary>
          <h3 class="settings-subheading-major">System Access</h3>
          <p class="settings-help" id="access-platform-help">JARVIS asks only when you use a feature. This check shows actual operating-system permissions.</p>
          <h4 class="settings-subheading">Operating-system permissions</h4>
          <div class="status-grid access-grid">
            <div class="status-row"><span class="status-dot" id="access-microphone"></span><span>Microphone</span><span class="status-detail" id="access-microphone-detail">Not checked</span><button class="access-manage" data-access-kind="microphone">Manage</button></div>
            <div class="status-row"><span class="status-dot" id="access-screen"></span><span>Screen capture</span><span class="status-detail" id="access-screen-detail">Not checked</span><button class="access-manage" data-access-kind="screen">Manage</button></div>
            <div class="status-row" data-macos-only><span class="status-dot" id="access-calendar"></span><span>Calendar automation</span><span class="status-detail" id="access-calendar-detail">Not checked</span><button class="access-manage" data-access-kind="automation">Manage</button></div>
            <div class="status-row" data-macos-only><span class="status-dot" id="access-mail"></span><span>Mail automation</span><span class="status-detail" id="access-mail-detail">Not checked</span><button class="access-manage" data-access-kind="automation">Manage</button></div>
            <div class="status-row" data-macos-only><span class="status-dot" id="access-notes"></span><span>Notes automation</span><span class="status-detail" id="access-notes-detail">Not checked</span><button class="access-manage" data-access-kind="automation">Manage</button></div>
            <div class="status-row"><span class="status-dot" id="access-files"></span><span>Desktop, Documents & Downloads</span><span class="status-detail" id="access-files-detail">Not checked</span><button class="access-manage" data-access-kind="files">Manage</button></div>
            <div class="status-row" data-macos-only><span class="status-dot" id="access-accessibility"></span><span>Accessibility control</span><span class="status-detail" id="access-accessibility-detail">Optional</span><button class="access-manage" data-access-kind="accessibility">Manage</button></div>
          </div>
          <h4 class="settings-subheading">Account and app capabilities</h4>
          <div class="status-grid access-grid">
            <div class="status-row"><span class="status-dot" id="access-browser-apps"></span><span>Websites, approved apps & folders</span><span class="status-detail" id="access-browser-apps-detail">Checking…</span></div>
            <div class="status-row"><span class="status-dot" id="access-gmail"></span><span>Private Gmail data</span><span class="status-detail" id="access-gmail-detail">Checking…</span><button class="access-manage" data-access-scroll="google-account-card">Connect</button></div>
            <div class="status-row"><span class="status-dot" id="access-google-calendar"></span><span>Private Google Calendar</span><span class="status-detail" id="access-google-calendar-detail">Checking…</span><button class="access-manage" data-access-scroll="google-account-card">Connect</button></div>
          </div>
          <div class="settings-actions">
            <button class="settings-btn primary" id="btn-check-access">Allow JARVIS once</button>
            <button class="settings-btn" id="btn-open-privacy">Privacy Settings</button>
          </div>
          </details>
          <div class="settings-feedback" id="access-feedback" role="status"></div>
        </section>

        <!-- Read-only support dashboard -->
        <section class="settings-section" id="section-tickets">
          <div class="ticket-heading">
            <div>
              <span class="settings-eyebrow">READ ONLY</span>
              <h3>Ticket overview</h3>
            </div>
            <span class="ticket-safety-badge">No clicks · no edits</span>
          </div>
          <p class="settings-help">Show ticket counts and a short summary from a public dashboard or from text you paste. JARVIS never signs in, clicks, submits, edits, or deletes anything.</p>

          <div class="ticket-input-grid">
            <div class="settings-field">
              <label for="input-ticket-workspace">Workspace name <span class="label-optional">optional</span></label>
              <input type="text" id="input-ticket-workspace" maxlength="80" autocomplete="off" placeholder="Customer Support" />
            </div>
            <div class="settings-field">
              <label for="input-ticket-url">Public HTTPS dashboard</label>
              <input type="url" id="input-ticket-url" maxlength="2048" autocomplete="off" placeholder="https://support.example.com/dashboard" />
              <p class="settings-help compact">Public pages only. Private or signed links, cookies, local addresses, and login sessions are blocked.</p>
            </div>
          </div>

          <div class="ticket-divider"><span>or paste visible ticket text</span></div>
          <div class="settings-field">
            <label for="input-ticket-snapshot">Dashboard text</label>
            <textarea id="input-ticket-snapshot" rows="7" maxlength="50000" autocomplete="off" placeholder="Total: 42&#10;Open: 8&#10;Pending: 3&#10;Urgent: 1"></textarea>
            <p class="settings-help compact">Pasted text is analyzed locally and cleared after a successful result. It is not sent to your AI provider.</p>
          </div>
          <div class="settings-actions">
            <button class="settings-btn primary" id="btn-analyze-tickets" type="button">Analyze tickets</button>
            <button class="settings-btn" id="btn-clear-tickets" type="button">Clear locally</button>
          </div>
          <div class="settings-feedback" id="ticket-feedback" role="status"></div>

          <div class="ticket-result" id="ticket-result" hidden>
            <div class="ticket-result-heading">
              <div><span>Latest read-only snapshot</span><strong id="ticket-result-title">Ticket overview</strong></div>
              <span class="ticket-local-chip">LOCAL SUMMARY</span>
            </div>
            <div class="ticket-metrics" aria-label="Ticket metrics">
              <div><span>Total</span><strong id="ticket-metric-total">—</strong></div>
              <div><span>Open</span><strong id="ticket-metric-open">—</strong></div>
              <div><span>Pending</span><strong id="ticket-metric-pending">—</strong></div>
              <div><span>Urgent</span><strong id="ticket-metric-urgent">—</strong></div>
              <div><span>New</span><strong id="ticket-metric-new">—</strong></div>
              <div><span>Closed</span><strong id="ticket-metric-closed">—</strong></div>
            </div>
            <p class="ticket-summary" id="ticket-summary"></p>
            <p class="ticket-proof" id="ticket-proof">Read only · no cookies · no clicks · nothing sent to the AI provider</p>
          </div>
        </section>

        <!-- User Preferences -->
        <section class="settings-section" id="section-preferences">
          <h3>User Preferences</h3>

          <div class="settings-field">
            <label for="input-ui-language">Interface language</label>
            <select id="input-ui-language">
              <option value="auto">Automatic (system language)</option>
              <option value="de">German</option>
              <option value="en">English</option>
            </select>
          </div>

          <div class="settings-field">
            <label>Your Name</label>
            <input type="text" id="input-user-name" placeholder="Your name" />
          </div>

          <div class="settings-field">
            <label>Honorific</label>
            <select id="input-honorific">
              <option value="sir">Sir</option>
              <option value="ma'am">Ma'am</option>
              <option value="none">None</option>
            </select>
          </div>

          <div class="settings-field" data-macos-only>
            <label>Calendar Accounts</label>
            <textarea id="input-calendar-accounts" rows="2" placeholder="auto (or comma-separated emails)"></textarea>
          </div>

          <div class="settings-actions">
            <button class="settings-btn primary" id="btn-save-prefs">Save Preferences</button>
          </div>
          <div class="settings-feedback" id="preferences-feedback" role="status"></div>
        </section>

        <!-- System Info -->
        <section class="settings-section" id="section-sysinfo">
          <h3>System Info</h3>
          <div class="sysinfo-grid">
            <div class="sysinfo-row"><span class="sysinfo-label">Memory entries</span><span id="sysinfo-memory">--</span></div>
            <div class="sysinfo-row"><span class="sysinfo-label">Tasks</span><span id="sysinfo-tasks">--</span></div>
            <div class="sysinfo-row"><span class="sysinfo-label">Server port</span><span id="sysinfo-port">--</span></div>
            <div class="sysinfo-row"><span class="sysinfo-label">Uptime</span><span id="sysinfo-uptime">--</span></div>
          </div>
        </section>

        <section class="settings-section settings-danger-zone" id="section-privacy-reset">
          <h3>Privacy & Reset</h3>
          <p class="settings-help">Remove saved keys, memory, tasks, preferences, usage records, and the offline voice pack from this computer. JARVIS shows a final confirmation before deleting anything.</p>
          <div class="settings-actions">
            <button class="settings-btn danger" id="btn-delete-local-data">Delete all local JARVIS data…</button>
          </div>
          <div class="settings-feedback" id="privacy-feedback" role="status"></div>
        </section>

        <!-- Setup Navigation (first-time only) -->
        <div class="setup-nav" id="setup-nav" style="display:none">
          <button class="settings-btn primary" id="btn-setup-next">Next</button>
        </div>

      </div>
    </div>
  `;
}

// ---------------------------------------------------------------------------
// Panel lifecycle
// ---------------------------------------------------------------------------

function createPanel(): HTMLElement {
  const container = document.createElement("div");
  container.id = "settings-container";
  container.innerHTML = buildPanelHTML();
  document.body.appendChild(container);
  translateDom(container);
  return container;
}

function setDotStatus(id: string, status: "green" | "red" | "yellow" | "off") {
  const dot = document.getElementById(id);
  if (!dot) return;
  dot.className = "status-dot";
  if (status !== "off") dot.classList.add(`status-${status}`);
}

function formatUptime(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function providerLabel(provider: string): string {
  return provider in LLM_PRESETS ? LLM_PRESETS[provider as LLMProvider].label : provider;
}

function voiceLabel(provider: StatusResponse["tts"]["active_provider"]): string {
  return {
    openai: "OpenAI voice",
    local: "Offline voice",
    fish: "Fish Audio",
    system: "System voice",
    unavailable: "Text only",
  }[provider];
}

function renderSystemHealth(status: StatusResponse) {
  const service = document.getElementById("health-service");
  const intelligence = document.getElementById("health-intelligence");
  const intelligenceDetail = document.getElementById("health-intelligence-detail");
  const voice = document.getElementById("health-voice");
  const chip = document.getElementById("system-health-chip");
  if (service) service.textContent = "Online";
  if (intelligence) intelligence.textContent = status.llm_ready ? "Ready" : "Setup needed";
  if (intelligenceDetail) intelligenceDetail.textContent = providerLabel(status.llm_provider);
  if (voice) voice.textContent = voiceLabel(status.tts.active_provider);
  if (chip) {
    chip.textContent = status.llm_ready ? "Core ready" : "Setup needed";
    chip.classList.toggle("is-ready", status.llm_ready);
    chip.classList.toggle("needs-attention", !status.llm_ready);
  }
}

async function loadDiagnostics() {
  const desktop = getDesktopBridge();
  const runtime = getRuntimeConfig();
  const version = document.getElementById("system-app-version");
  const platform = document.getElementById("system-platform");
  const keyProtection = document.getElementById("system-key-protection");
  if (version) version.textContent = runtime.appVersion ? `v${runtime.appVersion}` : "Web preview";
  if (platform) {
    const names: Record<string, string> = { darwin: "macOS", win32: "Windows", linux: "Linux" };
    platform.textContent = `${names[runtime.platform] || runtime.platform}${runtime.arch ? ` · ${runtime.arch}` : ""}`;
  }
  if (!desktop) {
    if (keyProtection) keyProtection.textContent = "Browser session";
    return null;
  }
  try {
    const report: DiagnosticsReport = await desktop.getDiagnostics();
    if (version) version.textContent = `v${report.app.version}`;
    if (keyProtection) keyProtection.textContent = report.key_storage.protected_by_operating_system
      ? `${platformPresentation().storageName} protected`
      : report.key_storage.mode === "local" ? "Private local file" : "Not available";
    return report;
  } catch (error) {
    if (keyProtection) keyProtection.textContent = "Status unavailable";
    setSectionFeedback("support-feedback", error instanceof Error ? error.message : "Could not load diagnostics.", true);
    return null;
  }
}

function selectedLLMProvider(): LLMProvider {
  const value = (document.getElementById("input-llm-provider") as HTMLSelectElement | null)?.value;
  return value && value in LLM_PRESETS ? value as LLMProvider : "openai";
}

/** Which pack the backend resolved, so saving does not reset a manual choice. */
let currentVoicePackChoice = "auto";

/** Say plainly which cloned JARVIS voice the language setting selected. */
function renderVoiceLanguageState(status: StatusResponse) {
  currentVoicePackChoice = status.tts.voice_pack_choice || "auto";
  const state = document.getElementById("voice-language-state");
  if (state) state.textContent = voiceLanguageStateText(status.tts);
}

function renderLocalModelReadiness(status: StatusResponse) {
  const state = document.getElementById("local-model-status");
  const start = document.getElementById("btn-start-local-runtime") as HTMLButtonElement | null;
  const install = document.getElementById("btn-install-local-model") as HTMLButtonElement | null;
  if (!state || status.llm_provider !== "ollama") return;
  const readiness = status.llm_readiness;
  start?.toggleAttribute("hidden", !readiness.runtime_installed || readiness.service_available);
  if (install) install.disabled = !readiness.service_available;
  if (readiness.ready) {
    setDotStatus("status-ollama", "green");
    state.textContent = `Local AI ready · ${status.llm_model} · no API key.`;
    return;
  }
  if (!readiness.runtime_installed) {
    setDotStatus("status-ollama", "red");
    state.textContent = "Ollama is not installed yet. Select Get Ollama, finish the installer, then reopen JARVIS.";
    return;
  }
  if (!readiness.service_available) {
    setDotStatus("status-ollama", "yellow");
    state.textContent = "Ollama is installed but its local service is stopped. Select Start local AI.";
    return;
  }
  const preferred = [
    status.llm_model,
    "qwen3.5:9b",
    "qwen3.5:4b",
    "qwen3.5:latest",
    ...readiness.installed_models,
  ].find((model, index, values) => model && readiness.installed_models.includes(model) && values.indexOf(model) === index);
  if (preferred) {
    (document.getElementById("input-llm-model") as HTMLInputElement).value = preferred;
    (document.getElementById("input-research-model") as HTMLInputElement).value = preferred;
    setDotStatus("status-ollama", "yellow");
    state.textContent = `${status.llm_model} is not installed. ${preferred} is available and selected — Save & restart to use it.`;
  } else {
    setDotStatus("status-ollama", "red");
    state.textContent = `${status.llm_model} is not installed. Install Qwen 3.5 9B to enable local intelligence.`;
  }
}

function updateProviderFields(provider: LLMProvider, applyDefaults = false) {
  const preset = LLM_PRESETS[provider];
  document.querySelectorAll<HTMLElement>(".provider-key-field").forEach((element) => {
    element.hidden = element.dataset.providerKey !== provider;
  });
  const baseField = document.getElementById("llm-base-url-field");
  if (baseField) baseField.hidden = provider === "anthropic";
  const localModelActions = document.getElementById("local-model-actions");
  if (localModelActions) localModelActions.hidden = provider !== "ollama";
  const research = document.getElementById("input-research-model") as HTMLInputElement | null;
  const researchField = research?.closest<HTMLElement>(".settings-field");
  if (researchField) researchField.hidden = provider === "openai";
  if (provider === "openai" && research) {
    const chat = document.getElementById("input-llm-model") as HTMLInputElement | null;
    research.value = chat?.value.trim() || preset.model;
  }
  const note = document.getElementById("llm-provider-note");
  if (note) note.textContent = preset.note;
  const keyLink = document.getElementById("llm-provider-key-link") as HTMLAnchorElement | null;
  if (keyLink) {
    keyLink.hidden = !preset.keyUrl;
    keyLink.href = preset.keyUrl || "#";
    keyLink.textContent = provider === "ollama"
      ? "Download Ollama ↗"
      : provider === "openai"
        ? "Create an OpenAI key ↗"
        : `Create a ${preset.label} key ↗`;
  }

  if (applyDefaults) {
    const base = document.getElementById("input-llm-base-url") as HTMLInputElement | null;
    const model = document.getElementById("input-llm-model") as HTMLInputElement | null;
    const research = document.getElementById("input-research-model") as HTMLInputElement | null;
    if (base) base.value = preset.baseUrl;
    if (model) model.value = preset.model;
    if (research) research.value = preset.researchModel;
  }
}

async function loadStatus() {
  try {
    const status = await apiGet<StatusResponse>("/api/settings/status");

    setDotStatus("status-claude-cli", status.claude_code_installed ? "green" : "red");
    setDotStatus("status-calendar", status.calendar_accessible ? "green" : "red");
    setDotStatus("status-mail", status.mail_accessible ? "green" : "red");
    setDotStatus("status-notes", status.notes_accessible ? "green" : "red");
    setDotStatus("status-server", "green");
    setDotStatus("status-browser-apps", status.capabilities.browser_and_apps ? "green" : "red");
    setDotStatus("status-local-listening", status.capabilities.local_voice_input ? "green" : "red");
    setDotStatus("status-screen-capture", status.capabilities.screen_capture ? "green" : "red");
    setDotStatus("status-private-notes", status.capabilities.private_notes ? "green" : "red");
    setDotStatus("status-google-account", status.capabilities.google_account_connected ? "green" : "yellow");
    renderSystemHealth(status);
    if (getRuntimeConfig().platform === "win32") {
      renderConnectionRow("calendar", status.calendar_accessible ? "available" : "unavailable");
      renderConnectionRow("mail", status.mail_accessible ? "available" : "unavailable");
    }

    const browserAppsDetail = document.getElementById("status-browser-apps-detail");
    const localListeningDetail = document.getElementById("status-local-listening-detail");
    const screenCaptureDetail = document.getElementById("status-screen-capture-detail");
    const privateNotesDetail = document.getElementById("status-private-notes-detail");
    const googleAccountDetail = document.getElementById("status-google-account-detail");
    if (browserAppsDetail) browserAppsDetail.textContent = status.capabilities.browser_and_apps ? "safe controls ready" : "unavailable";
    if (localListeningDetail) localListeningDetail.textContent = status.capabilities.local_voice_input ? "Whisper ready" : "fallback only";
    if (screenCaptureDetail) screenCaptureDetail.textContent = status.capabilities.screen_capture ? "on request" : "unavailable";
    if (privateNotesDetail) privateNotesDetail.textContent = status.capabilities.private_notes ? "stored on this computer" : "unavailable";
    if (googleAccountDetail) googleAccountDetail.textContent = status.capabilities.google_account_connected ? "connected" : "browser only";
    renderConnectedCapability(
      "browser-apps",
      status.capabilities.browser_and_apps,
      "Approved catalogue ready",
      "Unavailable",
    );
    renderConnectedCapability(
      "gmail",
      status.capabilities.google_account_connected,
      "Mail metadata + sending ready",
      "Browser only — not private mail",
    );
    renderConnectedCapability(
      "google-calendar",
      status.capabilities.google_account_connected,
      "Read-only connected",
      "Browser only — not private events",
    );
    document.querySelectorAll<HTMLButtonElement>("[data-access-scroll='google-account-card']").forEach((button) => {
      button.textContent = status.capabilities.google_account_connected ? "Manage" : "Connect";
    });

    const googleConnected = status.capabilities.google_account_connected;
    googleAccountConnected = googleConnected;
    for (const id of ["google", "gcal"]) {
      document.getElementById(`conn-${id}-dot`)?.classList.toggle("is-ready", googleConnected);
      const state = document.getElementById(`conn-${id}-state`);
      if (state) state.textContent = googleConnected ? "Connected" : "Not connected";
      const link = document.getElementById(`conn-${id}-dot`)
        ?.closest(".connection-row")
        ?.querySelector<HTMLElement>(".connection-link:not(.is-static)");
      if (link) link.textContent = googleConnected ? "Manage" : "Connect";
    }
    const googleState = document.getElementById("google-account-state");
    const googleBadge = document.getElementById("google-account-badge");
    const googleFields = document.getElementById("google-oauth-fields");
    const connectGoogle = document.getElementById("btn-connect-google");
    const disconnectGoogle = document.getElementById("btn-disconnect-google");
    if (googleState) googleState.textContent = status.capabilities.google_account_connected ? "Gmail & Calendar connected" : "Not connected";
    if (googleBadge) {
      googleBadge.textContent = status.capabilities.google_account_connected ? "CONNECTED" : "OFF";
      googleBadge.classList.toggle("is-ready", status.capabilities.google_account_connected);
    }
    if (googleFields) googleFields.hidden = status.capabilities.google_account_connected;
    if (connectGoogle) connectGoogle.hidden = status.capabilities.google_account_connected;
    if (disconnectGoogle) disconnectGoogle.hidden = !status.capabilities.google_account_connected;

    const llmProviderEl = document.getElementById("input-llm-provider") as HTMLSelectElement | null;
    const llmBaseEl = document.getElementById("input-llm-base-url") as HTMLInputElement | null;
    const llmModelEl = document.getElementById("input-llm-model") as HTMLInputElement | null;
    const researchModelEl = document.getElementById("input-research-model") as HTMLInputElement | null;
    if (llmProviderEl) llmProviderEl.value = status.llm_provider;
    if (llmBaseEl) llmBaseEl.value = status.llm_base_url || LLM_PRESETS[status.llm_provider].baseUrl;
    if (llmModelEl) llmModelEl.value = status.llm_model;
    if (researchModelEl) researchModelEl.value = status.research_model;
    updateProviderFields(status.llm_provider);
    renderLocalModelReadiness(status);

    const providerEl = document.getElementById("input-voice-provider") as HTMLSelectElement | null;
    const fishVoiceIdEl = document.getElementById("input-fish-voice-id") as HTMLInputElement | null;
    const voiceEl = document.getElementById("input-system-voice") as HTMLInputElement | null;
    const rateEl = document.getElementById("input-system-rate") as HTMLInputElement | null;
    const orbEl = document.getElementById("input-orb-style") as HTMLSelectElement | null;
    const wakeEl = document.getElementById("input-wake-mode") as HTMLSelectElement | null;
    const languageEl = document.getElementById("input-speech-language") as HTMLSelectElement | null;
    if (providerEl) providerEl.value = status.tts.configured_provider || "system";
    if (fishVoiceIdEl) fishVoiceIdEl.value = status.tts.reference_voice_id || "";
    if (voiceEl) voiceEl.value = status.tts.system_voice_configured || "Auto";
    if (rateEl) rateEl.value = String(status.tts.system_rate || 165);
    if (orbEl) {
      const saved = localStorage.getItem("jarvis_orb_style");
      orbEl.value = saved === "classic" ? "classic" : saved === "video" ? "video" : "live";
    }
    if (wakeEl) wakeEl.value = status.tts.wake_enabled ? "on" : "off";
    if (languageEl) languageEl.value = status.tts.speech_language || localStorage.getItem("jarvis_speech_language") || "auto";
    renderVoiceLanguageState(status);

    const sttEl = document.getElementById("input-stt-provider") as HTMLSelectElement | null;
    if (sttEl) sttEl.value = status.stt.configured_provider || "local";

    const speechEngineState = document.getElementById("speech-engine-state");
    const speechHelp = document.getElementById("speech-recognition-help");
    const sttLabels: Record<StatusResponse["stt"]["active_provider"], string> = {
      openai: `Cloud recognition · OpenAI ${status.stt.model || ""}`.trim(),
      fish: "Cloud recognition · Fish Audio",
      local: `On this computer · bundled Whisper${status.stt.local_running ? " (model loaded)" : ""}`,
      off: "Dictation is switched off",
    };
    if (speechEngineState) {
      speechEngineState.textContent = sttLabels[status.stt.active_provider] || "No recognition engine available";
      speechEngineState.classList.toggle("is-ready", status.stt.active_provider !== "off");
    }
    if (speechHelp) {
      const hardMemoryCap = ["win32", "linux"].includes(getRuntimeConfig().platform)
        ? ` Memory is hard-limited to ${(status.stt.local_memory_budget_mb / 1024).toFixed(1)} GiB.`
        : "";
      speechHelp.textContent = status.stt.cloud
        ? "Short microphone windows are sent to the selected speech provider, so this computer spends no processor time on recognition. The bundled offline engine stays as a fallback."
        : `Short microphone windows are transcribed only on this computer by bundled Whisper. Nothing is sent to a speech provider, but recognition uses the processor and keeps a model in memory.${hardMemoryCap}`;
    }

    const activeVoice = document.getElementById("voice-active-state");
    if (activeVoice) {
      const activeLabels: Record<StatusResponse["tts"]["active_provider"], string> = {
        openai: `OpenAI voice · ${status.tts.openai_voice || "cedar"}`,
        local: `Smooth JARVIS voice${status.tts.local_device ? ` · ${status.tts.local_device.toUpperCase()}` : ""}`,
        fish: "Fish Audio reference voice",
        system: `System voice · ${status.tts.system_voice || "default"}`,
        unavailable: "Unavailable — choose Automatic or install a voice pack",
      };
      activeVoice.textContent = activeLabels[status.tts.active_provider];
      activeVoice.classList.toggle("is-error", status.tts.active_provider === "unavailable");
    }

    const packState = document.getElementById("voice-pack-state");
    if (packState) {
      if (status.tts.local_ready) {
        const device = status.tts.local_device ? ` · ${status.tts.local_device.toUpperCase()}` : "";
        // Two packs can be installed, so name the one the language selected.
        const languages = (status.tts.local_languages || []).map((code) => code.toUpperCase()).join(" + ");
        packState.textContent = `Installed${languages ? ` · ${languages}` : ""}${status.tts.local_pack_version ? ` · v${status.tts.local_pack_version}` : ""}${device}`;
        packState.classList.add("is-ready");
      } else {
        packState.textContent = "Not activated · choose your existing .jarvisvoice file";
        packState.classList.remove("is-ready");
      }
    }

    const serverDetail = document.getElementById("status-server-detail");
    if (serverDetail) serverDetail.textContent = `port ${status.server_port} | up ${formatUptime(status.uptime_seconds)}`;

    // API key status dots
    setDotStatus("status-openai", status.env_keys_set.openai ? "green" : "red");
    setDotStatus("status-anthropic", status.env_keys_set.anthropic ? "green" : "red");
    setDotStatus("status-moonshot", status.env_keys_set.moonshot ? "green" : "red");
    setDotStatus("status-dashscope", status.env_keys_set.dashscope ? "green" : "red");
    setDotStatus("status-gemini", status.env_keys_set.gemini ? "green" : "red");
    setDotStatus("status-xai", status.env_keys_set.xai ? "green" : "red");
    setDotStatus("status-custom", status.env_keys_set.custom ? "green" : "off");
    setDotStatus("status-fish", status.env_keys_set.fish_audio ? "green" : "red");

    // System info
    const memEl = document.getElementById("sysinfo-memory");
    if (memEl) memEl.textContent = String(status.memory_count);
    const taskEl = document.getElementById("sysinfo-tasks");
    if (taskEl) taskEl.textContent = String(status.task_count);
    const portEl = document.getElementById("sysinfo-port");
    if (portEl) portEl.textContent = String(status.server_port);
    const upEl = document.getElementById("sysinfo-uptime");
    if (upEl) upEl.textContent = formatUptime(status.uptime_seconds);

    return status;
  } catch (e) {
    console.error("[settings] failed to load status:", e);
    setDotStatus("status-server", "red");
    return null;
  }
}

function renderAccessValue(id: string, value: AccessState) {
  const presentation = accessPresentation(value);
  setDotStatus(`access-${id}`, presentation.tone);
  const detail = document.getElementById(`access-${id}-detail`);
  if (detail) detail.textContent = presentation.label;
}

function renderConnectedCapability(id: string, ready: boolean, readyLabel: string, missingLabel: string) {
  setDotStatus(`access-${id}`, ready ? "green" : "yellow");
  const detail = document.getElementById(`access-${id}-detail`);
  if (detail) detail.textContent = ready ? readyLabel : missingLabel;
}

/** Mirror one permission into the plain-language connection list. */
function renderConnectionRow(id: string, value: AccessState) {
  const presentation = accessPresentation(value);
  const dot = document.getElementById(`conn-${id}-dot`);
  const state = document.getElementById(`conn-${id}-state`);
  const connected = presentation.tone === "green";
  if (dot) dot.classList.toggle("is-ready", connected);
  if (state) state.textContent = connected ? "Connected" : presentation.label;
  // Nothing left to do once a connection is live, so the button steps back.
  const row = dot?.closest(".connection-row");
  const link = row?.querySelector<HTMLElement>(".connection-link:not(.is-static)");
  if (link) link.hidden = connected;
}

function renderSystemAccess(status: SystemAccessStatus) {
  renderAccessValue("microphone", status.microphone);
  renderAccessValue("screen", status.screen);
  if (status.platform === "darwin") {
    renderAccessValue("calendar", status.automation.calendar);
    renderAccessValue("mail", status.automation.mail);
    renderAccessValue("notes", status.automation.notes);
  }
  renderAccessValue("files", status.files);
  renderAccessValue("accessibility", status.accessibility);

  renderConnectionRow("microphone", status.microphone);
  if (status.platform === "darwin") {
    renderConnectionRow("calendar", status.automation.calendar);
    renderConnectionRow("mail", status.automation.mail);
    renderConnectionRow("notes", status.automation.notes);
  }
  renderConnectionRow("files", status.files);

  const setupButton = document.getElementById("btn-check-access") as HTMLButtonElement | null;
  if (setupButton) {
    setupButton.dataset.setupDone = status.setup?.completed ? "true" : "false";
    setupButton.textContent = status.setup?.completed ? "Permission saved" : "Allow JARVIS once";
  }
}

async function loadSystemAccess(probeAutomation = false) {
  const desktop = getDesktopBridge();
  if (!desktop) {
    setSectionFeedback("access-feedback", "Permission diagnostics are available in the desktop app.");
    return null;
  }
  const status = await desktop.getSystemAccess({ probeAutomation });
  renderSystemAccess(status);
  return status;
}

function selectedSecretStorageMode(): "keychain" | "local" {
  const value = (document.getElementById("input-key-storage") as HTMLSelectElement | null)?.value;
  return value === "local" ? "local" : "keychain";
}

function renderSecretStorageStatus(status: SecretStorageStatus) {
  const select = document.getElementById("input-key-storage") as HTMLSelectElement | null;
  const help = document.getElementById("key-storage-help");
  const detail = document.getElementById("key-storage-detail");
  const storageName = platformPresentation().storageName;
  const inactiveButton = document.getElementById("btn-use-inactive-storage") as HTMLButtonElement | null;
  if (select) select.value = status.mode;
  const keychainOnly = status.mode === "local"
    && status.hasKeychainSecrets === true
    && status.hasLocalSecrets !== true;
  if (help) {
    help.textContent = keychainOnly
      ? `Password-free mode is active, but your previously saved key is still in ${storageName}.`
      : status.mode === "local"
        ? `Password-free mode is active. JARVIS does not open ${storageName}.`
        : `Keys are protected by ${storageName}. Your operating system may ask you to approve access after an app update.`;
  }
  if (detail) {
    detail.textContent = keychainOnly
      ? `To use that key, select ${storageName} below. To stay password-free, paste the key again and select Save & restart.`
      : status.mode === "local"
        ? "Saved only in JARVIS v4's private user folder. Other software running as the same operating-system user could still read it."
        : "Recommended for maximum protection. Select Local file if you cannot approve the operating-system security prompt.";
  }
  if (inactiveButton) {
    const useKeychain = status.mode === "local" && status.hasKeychainSecrets === true && status.hasLocalSecrets !== true;
    const useLocal = status.mode === "keychain" && status.hasLocalSecrets === true && status.hasKeychainSecrets !== true;
    inactiveButton.hidden = !useKeychain && !useLocal;
    inactiveButton.dataset.storageMode = useKeychain ? "keychain" : "local";
    inactiveButton.textContent = useKeychain
      ? `Use saved key from ${storageName}`
      : "Use saved key from private local file";
  }
}

async function loadSecretStorageStatus() {
  const desktop = getDesktopBridge();
  const field = document.getElementById("desktop-storage-field");
  if (!desktop) {
    if (field) field.hidden = true;
    return;
  }
  if (field) field.hidden = false;
  try {
    renderSecretStorageStatus(await desktop.getSecretStorageStatus());
  } catch {
    renderSecretStorageStatus({
      mode: "keychain",
      requiresPassword: false,
      storageBackend: "unavailable",
      secureStorageAvailable: false,
    });
  }
}

async function playBase64Audio(base64: string, mime = "audio/mpeg"): Promise<void> {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index++) bytes[index] = binary.charCodeAt(index);
  const url = URL.createObjectURL(new Blob([bytes], { type: mime }));
  const audio = new Audio(url);
  try {
    await new Promise<void>((resolve, reject) => {
      let settled = false;
      const timeout = window.setTimeout(() => finish(new Error("Voice playback timed out.")), 60000);
      const finish = (error?: Error) => {
        if (settled) return;
        settled = true;
        window.clearTimeout(timeout);
        URL.revokeObjectURL(url);
        if (error) reject(error); else resolve();
      };
      audio.addEventListener("ended", () => finish(), { once: true });
      audio.addEventListener("error", () => finish(new Error("The generated voice audio could not be decoded.")), { once: true });
      void audio.play().catch((error) => finish(error instanceof Error ? error : new Error("Audio playback was refused.")));
    });
  } catch (error) {
    // Surface autoplay/decoder failures in Settings instead of reporting a
    // successful test while the user hears nothing.
    const detail = error instanceof Error ? error.message : "browser refused playback";
    throw new Error(`Audio playback failed: ${detail}. Click Test Voice again after interacting with the app.`);
  }
}

async function playConfiguredVoiceSample(): Promise<string> {
  const result = await apiGet<{ audio: string | null; mime?: string; error?: string; tts?: StatusResponse["tts"] }>("/api/tts-test");
  if (result.audio) {
    await playBase64Audio(result.audio, result.mime);
    return result.tts?.last_provider || result.tts?.active_provider || "configured voice";
  }
  if (result.tts?.configured_provider !== "off" && browserSpeech.isSupported()) {
    await browserSpeech.speak("JARVIS v4 voice systems are online, sir.");
    return "built-in system voice";
  }
  throw new Error(result.error || "Voice output is disabled or unavailable.");
}

async function loadPreferences() {
  try {
    const prefs = await apiGet<PreferencesResponse>("/api/settings/preferences");
    const uiLanguage = document.getElementById("input-ui-language") as HTMLSelectElement | null;
    if (uiLanguage) {
      const stored = localStorage.getItem("jarvis_ui_language");
      uiLanguage.value = stored === "de" || stored === "en" ? stored : "auto";
    }
    const nameEl = document.getElementById("input-user-name") as HTMLInputElement;
    const honEl = document.getElementById("input-honorific") as HTMLSelectElement;
    const calEl = document.getElementById("input-calendar-accounts") as HTMLTextAreaElement;
    if (nameEl) nameEl.value = prefs.user_name || "";
    if (honEl) honEl.value = prefs.honorific || "sir";
    if (calEl) calEl.value = prefs.calendar_accounts || "auto";
  } catch (e) {
    console.error("[settings] failed to load preferences:", e);
  }
}

async function saveVoiceSettings(reloadAnimation = true) {
  const provider = (document.getElementById("input-voice-provider") as HTMLSelectElement).value;
  const system_voice = (document.getElementById("input-system-voice") as HTMLInputElement).value.trim() || "Auto";
  const system_rate = Number((document.getElementById("input-system-rate") as HTMLInputElement).value) || 165;
  const selectedOrbStyle = (document.getElementById("input-orb-style") as HTMLSelectElement).value;
  const orbStyle = selectedOrbStyle === "classic" ? "classic" : selectedOrbStyle === "video" ? "video" : "live";
  const wakeEnabled = (document.getElementById("input-wake-mode") as HTMLSelectElement).value !== "off";
  const speechLanguage = (document.getElementById("input-speech-language") as HTMLSelectElement).value || "auto";
  const sttProvider = (document.getElementById("input-stt-provider") as HTMLSelectElement | null)?.value || "auto";
  await apiPost("/api/settings/voice", {
    provider,
    system_voice,
    system_rate,
    speech_language: speechLanguage,
    stt_provider: sttProvider,
    wake_enabled: wakeEnabled,
    // "auto" lets the language above pick the pack; an explicit choice set
    // outside the interface is preserved rather than reset on every save.
    voice_pack: currentVoicePackChoice,
  });
  const savedOrbStyle = localStorage.getItem("jarvis_orb_style");
  const previousOrbStyle = savedOrbStyle === "classic" ? "classic" : savedOrbStyle === "video" ? "video" : "live";
  localStorage.setItem("jarvis_orb_style", orbStyle);
  localStorage.setItem("jarvis_wake_enabled", wakeEnabled ? "1" : "0");
  localStorage.setItem("jarvis_speech_language", speechLanguage);
  window.dispatchEvent(new CustomEvent("jarvis:wake-setting", { detail: { enabled: wakeEnabled, language: speechLanguage } }));
  if (reloadAnimation && orbStyle !== previousOrbStyle) {
    setSectionFeedback("voice-feedback", "Saved. Reloading the selected animation…");
    window.setTimeout(() => window.location.reload(), 350);
  } else {
    setSectionFeedback("voice-feedback", "Voice settings saved.");
    await loadStatus();
  }
}

async function saveLanguageModelSettings(): Promise<LLMProvider> {
  const provider = selectedLLMProvider();
  const base_url = (document.getElementById("input-llm-base-url") as HTMLInputElement).value.trim();
  const model = (document.getElementById("input-llm-model") as HTMLInputElement).value.trim();
  const research_model = provider === "openai"
    ? model
    : (document.getElementById("input-research-model") as HTMLInputElement).value.trim();
  const keys = {
    openai: (document.getElementById("input-openai-key") as HTMLInputElement).value.trim(),
    anthropic: (document.getElementById("input-anthropic-key") as HTMLInputElement).value.trim(),
    kimi: (document.getElementById("input-moonshot-key") as HTMLInputElement).value.trim(),
    qwen: (document.getElementById("input-dashscope-key") as HTMLInputElement).value.trim(),
    gemini: (document.getElementById("input-gemini-key") as HTMLInputElement).value.trim(),
    grok: (document.getElementById("input-xai-key") as HTMLInputElement).value.trim(),
    custom: (document.getElementById("input-custom-key") as HTMLInputElement).value.trim(),
    ollama: "",
  };
  const test = await apiPost<{ valid: boolean; error?: string }>("/api/settings/test-llm", {
    provider,
    key_value: keys[provider] || undefined,
    base_url,
    model,
  });
  if (!test.valid) throw new Error(test.error || "The language provider rejected these settings.");
  await apiPost("/api/settings/llm", { provider, base_url, model, research_model });
  const desktop = getDesktopBridge();
  if (desktop) {
    const result = await desktop.saveSecrets({
      storageMode: selectedSecretStorageMode(),
      openaiApiKey: keys.openai || undefined,
      anthropicApiKey: keys.anthropic || undefined,
      moonshotApiKey: keys.kimi || undefined,
      dashscopeApiKey: keys.qwen || undefined,
      geminiApiKey: keys.gemini || undefined,
      xaiApiKey: keys.grok || undefined,
      openaiCompatibleApiKey: keys.custom || undefined,
    });
    if (!result.success) throw new Error(result.error || "Key storage is unavailable");
    await waitForBackend();
  } else {
    const browserKeys: Array<[string, string]> = [
      ["OPENAI_API_KEY", keys.openai],
      ["ANTHROPIC_API_KEY", keys.anthropic],
      ["MOONSHOT_API_KEY", keys.kimi],
      ["DASHSCOPE_API_KEY", keys.qwen],
      ["GEMINI_API_KEY", keys.gemini],
      ["XAI_API_KEY", keys.grok],
      ["OPENAI_COMPATIBLE_API_KEY", keys.custom],
    ];
    for (const [key_name, key_value] of browserKeys) {
      if (key_value) await apiPost("/api/settings/keys", { key_name, key_value });
    }
  }
  for (const id of ["input-openai-key", "input-anthropic-key", "input-moonshot-key", "input-dashscope-key", "input-gemini-key", "input-xai-key", "input-custom-key"]) {
    (document.getElementById(id) as HTMLInputElement).value = "";
  }
  await loadStatus();
  return provider;
}

async function savePreferences() {
  const ui_language = (document.getElementById("input-ui-language") as HTMLSelectElement | null)?.value || "auto";
  const previousUiLanguage = getUiLanguage();
  setUiLanguage(ui_language as "auto" | "de" | "en");
  const user_name = (document.getElementById("input-user-name") as HTMLInputElement).value.trim();
  const honorific = (document.getElementById("input-honorific") as HTMLSelectElement).value;
  const calendar_accounts = (document.getElementById("input-calendar-accounts") as HTMLTextAreaElement).value.trim();
  await apiPost("/api/settings/preferences", { user_name, honorific, calendar_accounts });
  await loadStatus();
  if (getUiLanguage() !== previousUiLanguage) window.location.reload();
}

const TICKET_METRIC_NAMES = ["total", "open", "pending", "urgent", "new", "closed"] as const;

function clearTicketDashboard() {
  for (const id of ["input-ticket-workspace", "input-ticket-url", "input-ticket-snapshot"]) {
    const input = document.getElementById(id) as HTMLInputElement | HTMLTextAreaElement | null;
    if (input) input.value = "";
  }
  localStorage.removeItem("jarvis_ticket_workspace");
  localStorage.removeItem("jarvis_ticket_public_url");
  const result = document.getElementById("ticket-result");
  if (result) result.hidden = true;
  setSectionFeedback("ticket-feedback", "Cleared from this computer.");
}

function renderTicketDashboard(result: TicketDashboardResponse) {
  const container = document.getElementById("ticket-result");
  const title = document.getElementById("ticket-result-title");
  const summary = document.getElementById("ticket-summary");
  if (title) title.textContent = result.title || "Ticket overview";
  if (summary) summary.textContent = result.summary;
  for (const metric of TICKET_METRIC_NAMES) {
    const element = document.getElementById(`ticket-metric-${metric}`);
    if (element) element.textContent = result.metrics[metric] === null
      ? "—"
      : String(result.metrics[metric]);
  }
  if (container) container.hidden = false;
}

async function analyzeTicketDashboard() {
  const workspace = document.getElementById("input-ticket-workspace") as HTMLInputElement | null;
  const url = document.getElementById("input-ticket-url") as HTMLInputElement | null;
  const snapshot = document.getElementById("input-ticket-snapshot") as HTMLTextAreaElement | null;
  const workspaceName = workspace?.value.trim() || "";
  const publicUrl = url?.value.trim() || "";
  const pastedText = snapshot?.value.trim() || "";
  if (!publicUrl && !pastedText) throw new Error("Enter a public HTTPS dashboard or paste its visible ticket text.");

  const result = await apiPost<TicketDashboardResponse>("/api/ticket-dashboard/analyze", {
    workspace_name: workspaceName,
    url: publicUrl,
    snapshot: pastedText,
    language: getUiLanguage(),
  });
  renderTicketDashboard(result);
  // Remember only the harmless form labels. Ticket content is deliberately
  // never retained in browser storage.
  localStorage.setItem("jarvis_ticket_workspace", workspaceName);
  if (publicUrl) localStorage.setItem("jarvis_ticket_public_url", publicUrl);
  else localStorage.removeItem("jarvis_ticket_public_url");
  if (snapshot) snapshot.value = "";
}

function wireEvents() {
  // Close
  document.getElementById("settings-close")?.addEventListener("click", closeSettings);
  document.getElementById("settings-backdrop")?.addEventListener("click", closeSettings);

  document.querySelectorAll<HTMLButtonElement>(".settings-nav-button").forEach((button) => {
    button.addEventListener("click", () => {
      showSettingsPage(button.dataset.settingsTarget || "section-api-keys");
    });
  });

  const ticketWorkspace = document.getElementById("input-ticket-workspace") as HTMLInputElement | null;
  const ticketUrl = document.getElementById("input-ticket-url") as HTMLInputElement | null;
  if (ticketWorkspace) ticketWorkspace.value = localStorage.getItem("jarvis_ticket_workspace") || "";
  if (ticketUrl) ticketUrl.value = localStorage.getItem("jarvis_ticket_public_url") || "";
  document.getElementById("btn-analyze-tickets")?.addEventListener("click", async (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    button.disabled = true;
    setSectionFeedback("ticket-feedback", "Reading safely and calculating locally…");
    try {
      await analyzeTicketDashboard();
      setSectionFeedback("ticket-feedback", "Read-only ticket overview updated.");
    } catch (error) {
      setSectionFeedback("ticket-feedback", error instanceof Error ? error.message : "Ticket analysis failed.", true);
    } finally {
      button.disabled = false;
    }
  });
  document.getElementById("btn-clear-tickets")?.addEventListener("click", clearTicketDashboard);

  // Ask the system first, and only fall back to its privacy settings when the
  // operating system cannot grant or verify access directly.
  document.querySelectorAll<HTMLButtonElement>("[data-access-kind]").forEach((button) => {
    button.addEventListener("click", async () => {
      const desktop = getDesktopBridge();
      if (!desktop) {
        setSectionFeedback("access-feedback", "Open the installed desktop app to manage system permissions.", true);
        return;
      }
      const kind = button.dataset.accessKind as "microphone" | "screen" | "automation" | "accessibility" | "files";
      button.disabled = true;
      try {
        const platform = platformPresentation();
        setSectionFeedback(
          "access-feedback",
          platform.mac
            ? "Asking macOS for permission — approve the prompt if it appears…"
            : `Checking ${platform.systemName} privacy controls…`,
        );
        if (kind === "microphone") await desktop.requestMicrophoneAccess();
        // Probing automation is what triggers the system's own consent prompt.
        const status = await desktop.getSystemAccess({ probeAutomation: kind === "automation" });
        renderSystemAccess(status);

        const granted = kind === "microphone"
          ? accessPresentation(status.microphone).ready
          : kind === "automation"
            ? ["calendar", "mail", "notes"].some((name) => status.automation[name as "calendar"] === "granted")
            : kind === "files"
              ? status.files === "granted"
              : kind === "screen"
                ? accessPresentation(status.screen).ready
                : accessPresentation(status.accessibility).ready;

        if (granted) {
          setSectionFeedback("access-feedback", "Granted — JARVIS can use it now.");
          return;
        }
        const result = await desktop.openPrivacySettings(kind);
        if (!result.success) throw new Error(result.error || "The privacy settings could not be opened.");
        setSectionFeedback(
          "access-feedback",
          `${platform.systemName} did not report this access as ready. ${platform.privacyButton} is open — enable JARVIS there, then return.`,
        );
      } catch (error) {
        setSectionFeedback("access-feedback", error instanceof Error ? error.message : "Permission settings could not be opened.", true);
      } finally {
        button.disabled = false;
      }
    });
  });

  document.querySelectorAll<HTMLButtonElement>(".access-manage[data-access-scroll]").forEach((button) => {
    button.addEventListener("click", () => {
      document.getElementById(button.dataset.accessScroll || "")?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  });

  document.getElementById("input-llm-provider")?.addEventListener("change", () => {
    updateProviderFields(selectedLLMProvider(), true);
  });

  document.getElementById("btn-start-local-runtime")?.addEventListener("click", async () => {
    const button = document.getElementById("btn-start-local-runtime") as HTMLButtonElement;
    const status = document.getElementById("local-model-status");
    button.disabled = true;
    setDotStatus("status-ollama", "yellow");
    if (status) status.textContent = "Starting the private local AI service…";
    try {
      await apiPost("/api/settings/local-runtime/start", {});
      await loadStatus();
    } catch (error) {
      setDotStatus("status-ollama", "red");
      if (status) status.textContent = error instanceof Error ? error.message : "The local AI service could not start.";
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("btn-detect-local-models")?.addEventListener("click", async () => {
    const button = document.getElementById("btn-detect-local-models") as HTMLButtonElement;
    const status = document.getElementById("local-model-status");
    const baseUrl = (document.getElementById("input-llm-base-url") as HTMLInputElement).value.trim();
    button.disabled = true;
    setDotStatus("status-ollama", "yellow");
    if (status) status.textContent = "Looking for the local Ollama service…";
    try {
      const result = await apiGet<{ available: boolean; models: string[]; error?: string }>(
        `/api/settings/local-models?base_url=${encodeURIComponent(baseUrl)}`,
      );
      if (!result.available) throw new Error(result.error || "Ollama is unavailable.");
      if (!result.models.length) throw new Error("Ollama is running, but no local model is installed yet. Install qwen3.5:9b, then try again.");
      const preferred = [
        (document.getElementById("input-llm-model") as HTMLInputElement).value.trim(),
        "qwen3.5:9b",
        "qwen3.5:4b",
        "qwen3.5:latest",
      ].find((model) => model && result.models.includes(model)) || result.models[0];
      (document.getElementById("input-llm-model") as HTMLInputElement).value = preferred;
      const research = (document.getElementById("input-research-model") as HTMLInputElement);
      if (!result.models.includes(research.value.trim())) research.value = preferred;
      setDotStatus("status-ollama", "green");
      if (status) status.textContent = `${result.models.length} installed model${result.models.length === 1 ? "" : "s"} found · selected ${preferred}.`;
    } catch (error) {
      setDotStatus("status-ollama", "red");
      if (status) status.textContent = error instanceof Error ? error.message : "Ollama could not be detected.";
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("btn-install-local-model")?.addEventListener("click", async () => {
    const button = document.getElementById("btn-install-local-model") as HTMLButtonElement;
    const detect = document.getElementById("btn-detect-local-models") as HTMLButtonElement;
    const status = document.getElementById("local-model-status");
    button.disabled = true;
    detect.disabled = true;
    setDotStatus("status-ollama", "yellow");
    if (status) status.textContent = "Starting the 6.6 GB local model download…";
    try {
      await apiPost("/api/settings/local-models/install", { model: "qwen3.5:9b" });
      for (let attempt = 0; attempt < 1800; attempt++) {
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const install = await apiGet<{ state: string; progress: string; error: string }>("/api/settings/local-models/install-status");
        if (status) status.textContent = install.progress || "Installing Qwen 3.5 9B…";
        if (install.state === "ready") {
          (document.getElementById("input-llm-model") as HTMLInputElement).value = "qwen3.5:9b";
          (document.getElementById("input-research-model") as HTMLInputElement).value = "qwen3.5:9b";
          setDotStatus("status-ollama", "green");
          if (status) status.textContent = "Qwen 3.5 9B is installed locally and ready. Select Test provider, then Save & restart.";
          return;
        }
        if (["error", "canceled"].includes(install.state)) throw new Error(install.error || "Model installation failed.");
      }
      throw new Error("The model installation is still running. Reopen Settings to check it again.");
    } catch (error) {
      setDotStatus("status-ollama", "red");
      if (status) status.textContent = error instanceof Error ? error.message : "Model installation failed.";
    } finally {
      button.disabled = false;
      detect.disabled = false;
    }
  });

  window.addEventListener("jarvis:wake-test-result", ((event: CustomEvent<{
    state: "listening" | "heard" | "success" | "timeout" | "unsupported" | "error";
    text?: string;
    error?: string;
  }>) => {
    const card = document.getElementById("wake-test-card");
    const state = document.getElementById("wake-test-state");
    const detail = document.getElementById("wake-test-detail");
    const button = document.getElementById("btn-test-wake") as HTMLButtonElement | null;
    if (!card || !state || !detail || !button) return;
    card.dataset.state = event.detail.state;
    const heard = (event.detail.text || "").trim();
    if (event.detail.state === "listening") {
      state.textContent = "Listening for 12 seconds…";
      detail.textContent = "Say “Hey JARVIS” clearly in the selected language.";
      button.disabled = true;
      button.textContent = "Listening…";
    } else if (event.detail.state === "heard") {
      state.textContent = "Microphone is hearing you";
      detail.textContent = heard ? `Heard “${heard}” — now say “Hey JARVIS”.` : "Now say “Hey JARVIS”.";
    } else if (event.detail.state === "success") {
      state.textContent = "Wake phrase recognized — testing reply…";
      detail.textContent = heard ? `Heard “${heard}”. Now checking audible output.` : "Now checking audible output.";
      button.disabled = true;
      button.textContent = "Playing reply…";
      void playConfiguredVoiceSample().then((provider) => {
        card.dataset.state = "success";
        state.textContent = "Voice conversation ready";
        detail.textContent = heard
          ? `Heard “${heard}” and played the reply via ${provider}.`
          : `Wake phrase and reply verified via ${provider}.`;
        localStorage.setItem("jarvis_voice_check_passed_at", new Date().toISOString());
        button.disabled = false;
        button.textContent = "Check again";
      }).catch((error) => {
        card.dataset.state = "error";
        state.textContent = "Wake phrase works; reply needs attention";
        detail.textContent = error instanceof Error ? error.message : "Voice output could not be verified.";
        button.disabled = false;
        button.textContent = "Try again";
      });
    } else {
      state.textContent = event.detail.state === "timeout" ? "Wake phrase not heard" : "Microphone test unavailable";
      detail.textContent = event.detail.error || "No matching wake phrase was recognized. Check the language and microphone permission, then try again.";
      button.disabled = false;
      button.textContent = "Try again";
    }
  }) as EventListener);

  document.getElementById("btn-test-wake")?.addEventListener("click", () => {
    const language = (document.getElementById("input-speech-language") as HTMLSelectElement | null)?.value || "auto";
    window.dispatchEvent(new CustomEvent("jarvis:wake-test-start", { detail: { language } }));
  });

  document.getElementById("input-key-storage")?.addEventListener("change", () => {
    const mode = selectedSecretStorageMode();
    renderSecretStorageStatus({
      mode,
      requiresPassword: mode === "keychain",
      storageBackend: mode === "local" ? "private-local-file" : "keychain",
      secureStorageAvailable: true,
    });
  });

  document.getElementById("btn-use-inactive-storage")?.addEventListener("click", async (event) => {
    const button = event.currentTarget as HTMLButtonElement;
    const mode = button.dataset.storageMode === "local" ? "local" : "keychain";
    const desktop = getDesktopBridge();
    if (!desktop) return;
    button.disabled = true;
    setFeedback("Activating the saved key and restarting JARVIS…");
    try {
      const result = await desktop.activateSecretStorage(mode);
      if (!result.success) throw new Error(result.error || "The saved key could not be activated.");
      await waitForBackend();
      await loadStatus();
      await loadSecretStorageStatus();
      setFeedback("Saved key activated. JARVIS is ready.");
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "The saved key could not be activated.", true);
    } finally {
      button.disabled = false;
    }
  });

  // Save provider configuration and any newly entered provider keys.
  document.getElementById("btn-save-llm")?.addEventListener("click", async () => {
    setFeedback("Testing and saving provider settings…");
    try {
      const provider = await saveLanguageModelSettings();
      const modeLabel = getDesktopBridge() && selectedSecretStorageMode() === "local"
        ? "saved in the private local file"
        : "saved securely";
      setFeedback(provider === "ollama"
        ? `${LLM_PRESETS[provider].label} verified and saved. Conversations stay on this computer.`
        : `${LLM_PRESETS[provider].label} verified and ${modeLabel}. Key values are never displayed again.`);
    } catch (error) {
      setFeedback(error instanceof Error ? error.message : "Could not save language provider", true);
    }
  });

  document.getElementById("btn-test-llm")?.addEventListener("click", async () => {
    const provider = selectedLLMProvider();
    const preset = LLM_PRESETS[provider];
    const keyInput = preset.keyInput ? document.getElementById(preset.keyInput) as HTMLInputElement | null : null;
    const key = keyInput?.value.trim() || "";
    const base_url = (document.getElementById("input-llm-base-url") as HTMLInputElement).value.trim();
    const model = (document.getElementById("input-llm-model") as HTMLInputElement).value.trim();
    const dotId = {
      ollama: "status-ollama",
      openai: "status-openai",
      anthropic: "status-anthropic",
      kimi: "status-moonshot",
      qwen: "status-dashscope",
      gemini: "status-gemini",
      grok: "status-xai",
      custom: "status-custom",
    }[provider];
    setDotStatus(dotId, "yellow");
    setFeedback("Testing " + preset.label + "…");
    try {
      const result = await apiPost<{ valid: boolean; error?: string }>("/api/settings/test-llm", {
        provider,
        key_value: key || undefined,
        base_url,
        model,
      });
      setDotStatus(dotId, result.valid ? "green" : "red");
      setFeedback(result.valid ? preset.label + " is ready." : result.error || "Provider test failed.", !result.valid);
    } catch (error) {
      setDotStatus(dotId, "red");
      setFeedback(error instanceof Error ? error.message : "Provider test failed.", true);
    }
  });

  // Save Fish Audio credentials separately from the language model.
  document.getElementById("btn-save-fish")?.addEventListener("click", async () => {
    const fishKey = (document.getElementById("input-fish-key") as HTMLInputElement).value.trim();
    const voiceId = (document.getElementById("input-fish-voice-id") as HTMLInputElement).value.trim();
    if (!fishKey && !voiceId) {
      setSectionFeedback("voice-feedback", "Enter a Fish key or voice ID first.", true);
      return;
    }
    setSectionFeedback("voice-feedback", "Saving Fish Audio settings…");
    try {
      if (fishKey) {
        const test = await apiPost<{ valid: boolean; error?: string }>("/api/settings/test-fish", {
          key_value: fishKey,
          voice_id: voiceId,
        });
        if (!test.valid) throw new Error(test.error || "Fish Audio rejected the key or voice.");
      }
      if (voiceId) await apiPost("/api/settings/keys", { key_name: "FISH_VOICE_ID", key_value: voiceId });
      const desktop = getDesktopBridge();
      if (desktop && fishKey) {
        const result = await desktop.saveSecrets({
          storageMode: selectedSecretStorageMode(),
          fishApiKey: fishKey,
        });
        if (!result.success) throw new Error(result.error || "Key storage is unavailable");
        await waitForBackend();
      } else if (fishKey) {
        await apiPost("/api/settings/keys", { key_name: "FISH_API_KEY", key_value: fishKey });
      }
      (document.getElementById("input-fish-key") as HTMLInputElement).value = "";
      const local = getDesktopBridge() && selectedSecretStorageMode() === "local";
      setSectionFeedback(
        "voice-feedback",
        fishKey ? `Fish Audio verified and saved ${local ? "in the private local file" : "with operating-system protection"}.` : "Fish Audio Voice ID saved.",
      );
      await loadStatus();
    } catch (error) {
      setSectionFeedback("voice-feedback", error instanceof Error ? error.message : "Could not save Fish Audio settings.", true);
    }
  });

  // Test Fish
  document.getElementById("btn-test-fish")?.addEventListener("click", async () => {
    setDotStatus("status-fish", "yellow");
    const key = (document.getElementById("input-fish-key") as HTMLInputElement).value.trim();
    const voiceId = (document.getElementById("input-fish-voice-id") as HTMLInputElement).value.trim();
    setSectionFeedback("voice-feedback", "Generating a Fish Audio sample…");
    try {
      const result = await apiPost<{ valid: boolean; error?: string; audio?: string; mime?: string }>("/api/settings/test-fish", {
        key_value: key || undefined,
        voice_id: voiceId,
      });
      setDotStatus("status-fish", result.valid ? "green" : "red");
      if (!result.valid) throw new Error(result.error || "Fish Audio test failed.");
      if (result.audio) await playBase64Audio(result.audio, result.mime);
      setSectionFeedback("voice-feedback", "Fish Audio is ready — playing the real JARVIS voice sample.");
    } catch (error) {
      setDotStatus("status-fish", "red");
      setSectionFeedback("voice-feedback", error instanceof Error ? error.message : "Fish Audio test failed.", true);
    }
  });

  document.getElementById("btn-save-voice")?.addEventListener("click", async () => {
    setSectionFeedback("voice-feedback", "Saving…");
    try {
      await saveVoiceSettings(true);
    } catch (error) {
      setSectionFeedback("voice-feedback", error instanceof Error ? error.message : "Could not save voice settings", true);
    }
  });

  document.getElementById("btn-test-voice")?.addEventListener("click", async () => {
    setSectionFeedback("voice-feedback", "Preparing voice test…");
    try {
      const provider = await playConfiguredVoiceSample();
      setSectionFeedback("voice-feedback", `Voice test completed via ${provider}.`);
    } catch (error) {
      setSectionFeedback("voice-feedback", error instanceof Error ? error.message : "Voice test failed", true);
    }
  });

  document.getElementById("btn-install-voice-pack")?.addEventListener("click", async () => {
    const desktop = getDesktopBridge();
    if (!desktop) {
      setSectionFeedback("voice-feedback", "Voice packs can be installed from the desktop app.", true);
      return;
    }
    const button = document.getElementById("btn-install-voice-pack") as HTMLButtonElement;
    button.disabled = true;
    setSectionFeedback("voice-feedback", "Installing and checking the voice pack… this can take a few minutes.");
    try {
      const result = await desktop.installVoicePack();
      if (result.canceled) {
        setSectionFeedback("voice-feedback", "Installation canceled.");
        return;
      }
      if (!result.success) throw new Error(result.error || "Voice pack installation failed");
      await waitForBackend();
      const selected = document.getElementById("input-voice-provider") as HTMLSelectElement;
      selected.value = "local";
      currentVoicePackChoice = "auto";
      await saveVoiceSettings(false);
      setSectionFeedback("voice-feedback", `Installed and activated ${result.name || "Smooth JARVIS Voice"}. Run Test Voice to hear it.`);
    } catch (error) {
      setSectionFeedback("voice-feedback", error instanceof Error ? error.message : "Voice pack installation failed", true);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("btn-check-access")?.addEventListener("click", async () => {
    const desktop = getDesktopBridge();
    if (!desktop) {
      setSectionFeedback("access-feedback", "Open JARVIS as a desktop app to check permissions.", true);
      return;
    }
    const button = document.getElementById("btn-check-access") as HTMLButtonElement;
    const platform = platformPresentation();
    if (button.dataset.setupDone === "true") {
      await loadSystemAccess(false);
      setSectionFeedback("access-feedback", `Your permission setup is saved. JARVIS will only ask again if ${platform.systemName} revokes access or the app identity changes.`);
      return;
    }
    button.disabled = true;
    setSectionFeedback("access-feedback", platform.permissionPrompt);
    try {
      const result = await desktop.requestAllSystemAccess();
      if (!result.success || !result.status) throw new Error(result.error || "The operating system did not return a permission status.");
      renderSystemAccess(result.status);
      const summary = summarizeCoreAccess(result.status.platform, result.status);
      setSectionFeedback(
        "access-feedback",
        result.needsManual?.length
          ? `Saved. Finish the highlighted items in the ${platform.privacyButton} window that opened; ${platform.systemName} will remember them.`
          : `Saved. ${summary.message} JARVIS will not ask again.`,
      );
    } catch (error) {
      setSectionFeedback("access-feedback", error instanceof Error ? error.message : "Permission check failed", true);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("btn-open-privacy")?.addEventListener("click", async () => {
    const desktop = getDesktopBridge();
    if (!desktop) return;
    const result = await desktop.openPrivacySettings("all");
    if (!result.success) setSectionFeedback("access-feedback", result.error || "Could not open Privacy Settings", true);
  });

  const revealGoogleSetup = (message: string, isError = true) => {
    showSettingsPage("section-access");
    const card = document.getElementById("google-account-card");
    const setup = document.getElementById("google-oauth-fields") as HTMLDetailsElement | null;
    if (isError && setup) {
      setup.hidden = false;
      setup.open = true;
    }
    card?.scrollIntoView({ behavior: "smooth", block: "center" });
    if (isError) (document.getElementById("input-google-client-id") as HTMLInputElement | null)?.focus();
    setSectionFeedback("google-feedback", message, isError);
  };

  const startGoogleConnection = async () => {
    if (googleAccountConnected) {
      revealGoogleSetup("Gmail and Google Calendar are connected. You can disconnect them here.", false);
      return;
    }
    const desktop = getDesktopBridge();
    const button = document.getElementById("btn-connect-google") as HTMLButtonElement | null;
    if (!desktop || !button) {
      setSectionFeedback("access-feedback", "Open the installed Windows app to connect Google.", true);
      return;
    }
    const clientId = (document.getElementById("input-google-client-id") as HTMLInputElement | null)?.value.trim() || undefined;
    const clientSecret = (document.getElementById("input-google-client-secret") as HTMLInputElement | null)?.value.trim() || undefined;
    button.disabled = true;
    setSectionFeedback("access-feedback", "Google opens in your browser. Approve the requested read access there…");
    setSectionFeedback("google-feedback", "Waiting for Google approval…");
    try {
      const result = await desktop.connectGoogle({ clientId, clientSecret, storageMode: selectedSecretStorageMode() });
      if (!result.success) throw new Error(result.error || "Google connection failed");
      const secretInput = document.getElementById("input-google-client-secret") as HTMLInputElement | null;
      if (secretInput) secretInput.value = "";
      setSectionFeedback("access-feedback", "Gmail and Google Calendar are connected.");
      setSectionFeedback("google-feedback", "Google connected successfully.");
      await loadStatus();
    } catch (error) {
      const message = error instanceof Error ? error.message : "Google connection failed";
      if (/OAuth client ID|required|client ID/i.test(message)) {
        revealGoogleSetup("This build needs its Google Desktop OAuth client ID once. Add it here, then select Connect.");
      } else {
        setSectionFeedback("access-feedback", message, true);
        setSectionFeedback("google-feedback", message, true);
      }
    } finally {
      button.disabled = false;
    }
  };

  // Clicking either the full branded row or its button starts the secure
  // consent flow directly. Keyboard users receive the same one-step action.
  document.querySelectorAll<HTMLElement>("[data-google-connect]").forEach((row) => {
    row.addEventListener("click", () => { void startGoogleConnection(); });
    row.addEventListener("keydown", (event) => {
      if (event.target !== row) return;
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      void startGoogleConnection();
    });
  });

  document.getElementById("btn-open-google-console")?.addEventListener("click", () => {
    // Straight to the credentials screen rather than the console front page.
    window.open("https://console.cloud.google.com/apis/credentials", "_blank", "noreferrer");
  });

  document.getElementById("btn-connect-google")?.addEventListener("click", () => { void startGoogleConnection(); });

  document.getElementById("btn-disconnect-google")?.addEventListener("click", async () => {
    const desktop = getDesktopBridge();
    if (!desktop) return;
    setSectionFeedback("google-feedback", "Waiting for confirmation…");
    const result = await desktop.disconnectGoogle();
    if (result.canceled) {
      setSectionFeedback("google-feedback", "Google remains connected.");
    } else if (!result.success) {
      setSectionFeedback("google-feedback", result.error || "Google could not be disconnected.", true);
    } else {
      setSectionFeedback("google-feedback", "Google disconnected and its local token was removed.");
      await loadStatus();
    }
  });

  document.getElementById("btn-delete-local-data")?.addEventListener("click", async () => {
    const desktop = getDesktopBridge();
    if (!desktop) {
      setSectionFeedback("privacy-feedback", "Local-data deletion is available in the desktop app.", true);
      return;
    }
    setSectionFeedback("privacy-feedback", "Waiting for your confirmation…");
    const result = await desktop.deleteAllLocalData();
    if (result.canceled) {
      setSectionFeedback("privacy-feedback", "Nothing was deleted.");
    } else if (!result.success) {
      setSectionFeedback("privacy-feedback", result.error || "Could not delete local data.", true);
    }
  });

  document.getElementById("btn-refresh-system")?.addEventListener("click", async () => {
    setSectionFeedback("support-feedback", "Refreshing system health…");
    const status = await loadStatus();
    await loadDiagnostics();
    setSectionFeedback("support-feedback", status ? "System health is up to date." : "The local service is not responding.", !status);
  });

  document.getElementById("btn-test-connections")?.addEventListener("click", async () => {
    const button = document.getElementById("btn-test-connections") as HTMLButtonElement;
    button.disabled = true;
    setSectionFeedback("support-feedback", "Testing the saved provider connections…");
    try {
      const status = await loadStatus();
      if (!status) throw new Error("The local JARVIS service is not responding.");
      const checks: string[] = ["local service ready"];
      let needsAttention = false;
      if (status.llm_ready) {
        const llm = await apiPost<{ valid: boolean; error?: string }>("/api/settings/test-llm", {
          provider: status.llm_provider,
          base_url: status.llm_base_url,
          model: status.llm_model,
        });
        if (!llm.valid) throw new Error(llm.error || "The language provider test failed.");
        checks.push(`${providerLabel(status.llm_provider)} verified`);
        const intelligence = document.getElementById("health-intelligence");
        if (intelligence) intelligence.textContent = "Verified";
      } else {
        checks.push("language model needs setup");
        needsAttention = true;
      }
      if (status.env_keys_set.fish_audio) {
        const fish = await apiPost<{ valid: boolean; error?: string }>("/api/settings/test-fish", {
          voice_id: status.tts.reference_voice_id,
          include_audio: false,
        });
        if (!fish.valid) throw new Error(fish.error || "The Fish Audio test failed.");
        checks.push("Fish Audio verified");
      } else {
        checks.push(`${voiceLabel(status.tts.active_provider)} ready`);
      }
      const chip = document.getElementById("system-health-chip");
      if (chip && !needsAttention) {
        chip.textContent = "Connections verified";
        chip.classList.add("is-ready");
        chip.classList.remove("needs-attention");
      }
      setSectionFeedback("support-feedback", `Check complete: ${checks.join(" · ")}.`, needsAttention);
    } catch (error) {
      setSectionFeedback("support-feedback", error instanceof Error ? error.message : "Connection test failed.", true);
    } finally {
      button.disabled = false;
    }
  });

  document.getElementById("btn-export-diagnostics")?.addEventListener("click", async () => {
    const desktop = getDesktopBridge();
    if (!desktop) {
      setSectionFeedback("support-feedback", "Diagnostic export is available in the desktop app.", true);
      return;
    }
    setSectionFeedback("support-feedback", "Preparing a privacy-safe diagnostic report…");
    const result = await desktop.exportDiagnostics();
    if (result.canceled) {
      setSectionFeedback("support-feedback", "Export canceled. Nothing was written.");
    } else if (result.success) {
      setSectionFeedback("support-feedback", `${result.fileName || "Diagnostic report"} saved. No keys, chats, memories, names, or personal paths were included.`);
    } else {
      setSectionFeedback("support-feedback", result.error || "The diagnostic report could not be saved.", true);
    }
  });

  // Save preferences
  document.getElementById("btn-save-prefs")?.addEventListener("click", async () => {
    setSectionFeedback("preferences-feedback", "Saving…");
    try {
      await savePreferences();
      setSectionFeedback("preferences-feedback", "Preferences saved.");
    } catch (error) {
      setSectionFeedback("preferences-feedback", error instanceof Error ? error.message : "Could not save preferences.", true);
    }
  });

  // Setup next button
  document.getElementById("btn-setup-next")?.addEventListener("click", advanceSetup);
}

function showSettingsPage(targetId: string) {
  if (isFirstTimeSetup || !SETTINGS_PAGES[targetId]) return;
  activeSettingsPage = targetId;
  const visible = new Set(SETTINGS_PAGES[targetId]);
  for (const sectionIds of Object.values(SETTINGS_PAGES)) {
    for (const sectionId of sectionIds) {
      const section = document.getElementById(sectionId);
      if (section) section.style.display = visible.has(sectionId) ? "" : "none";
    }
  }
  document.querySelectorAll<HTMLButtonElement>(".settings-nav-button").forEach((button) => {
    const selected = button.dataset.settingsTarget === targetId;
    button.classList.toggle("active", selected);
    button.setAttribute("aria-selected", String(selected));
    button.tabIndex = selected ? 0 : -1;
  });
  document.getElementById("settings-panel-inner")?.scrollTo({ top: 0, behavior: "smooth" });
}

// ---------------------------------------------------------------------------
// First-time setup wizard
// ---------------------------------------------------------------------------

function enterSetupMode() {
  isFirstTimeSetup = true;
  isPermissionOnlySetup = false;
  setupStep = 0;

  const welcome = document.getElementById("settings-welcome");
  if (welcome) welcome.style.display = "flex";

  const nav = document.getElementById("setup-nav");
  if (nav) nav.style.display = "flex";
  const sectionNav = document.getElementById("settings-section-nav");
  if (sectionNav) sectionNav.style.display = "none";

  // Hide sections except API keys
  showSetupStep(0);
}

/**
 * Put the operating-system consent in front of every other optional setting.
 * This also runs when an existing intelligence provider is already ready, so
 * a preconfigured install does not silently skip the one-time access setup.
 */
function enterPermissionSetupMode() {
  isFirstTimeSetup = true;
  isPermissionOnlySetup = true;
  setupStep = 2;

  const welcome = document.getElementById("settings-welcome");
  if (welcome) welcome.style.display = "flex";
  const nav = document.getElementById("setup-nav");
  if (nav) nav.style.display = "flex";
  const sectionNav = document.getElementById("settings-section-nav");
  if (sectionNav) sectionNav.style.display = "none";
  showSetupStep(2);
}

function showSetupStep(step: number) {
  const sections = ["section-api-keys", "section-voice", "section-status", "section-access", "section-tickets", "section-preferences", "section-sysinfo", "section-privacy-reset"];
  sections.forEach((id) => {
    const el = document.getElementById(id);
    if (!el) return;
    if (step === 0 && id === "section-api-keys") el.style.display = "";
    else if (step === 1 && id === "section-voice") el.style.display = "";
    else if (step === 2 && id === "section-access") el.style.display = "";
    else if (step === 3 && id === "section-preferences") el.style.display = "";
    else if (step === 4) el.style.display = "";
    else el.style.display = "none";
  });

  const progress = document.getElementById("setup-progress");
  const copy = document.getElementById("setup-copy");
  const setupCopy = [
    "Choose the intelligence JARVIS should use. You can change this later.",
    "Set up local listening and a voice, then run the conversation check.",
    "Review each permission. Private Gmail and Calendar stay disconnected until you explicitly connect them.",
    "Personalize how JARVIS addresses you, then finish setup.",
  ];
  if (progress) progress.textContent = `Step ${Math.min(step + 1, 4)} of 4`;
  if (copy) copy.textContent = setupCopy[step] || "Setup complete.";

  const nextBtn = document.getElementById("btn-setup-next");
  if (isPermissionOnlySetup) {
    if (progress) progress.textContent = "One-time access";
    if (copy) copy.textContent = "Allow JARVIS once at the beginning. Your operating system remembers the choice, so JARVIS does not ask again on later starts.";
    if (nextBtn) nextBtn.textContent = "Allow everything once";
    return;
  }
  if (nextBtn) {
    if (step === 0) nextBtn.textContent = "Next: Voice";
    else if (step === 1) nextBtn.textContent = "Next: Permissions";
    else if (step === 2) nextBtn.textContent = "Next: Set Your Name";
    else if (step === 3) nextBtn.textContent = "Finish Setup";
    else nextBtn.style.display = "none";
  }
}

async function advanceSetup() {
  const nextButton = document.getElementById("btn-setup-next") as HTMLButtonElement | null;
  if (nextButton?.disabled) return;
  if (nextButton) nextButton.disabled = true;
  let permissionOnlyCompleted = false;
  try {
    if (setupStep === 0) {
      setFeedback("Starting and verifying local intelligence… The first model start can take up to a minute.");
      const provider = await saveLanguageModelSettings();
      setFeedback(provider === "ollama"
        ? "Local intelligence verified and saved."
        : `${LLM_PRESETS[provider].label} verified and saved.`);
    }
    if (setupStep === 1) await saveVoiceSettings(false);
    if (setupStep === 2) {
      const desktop = getDesktopBridge();
      const status = await loadSystemAccess(false);
      if (desktop && !status?.setup?.completed) {
        const result = await desktop.requestAllSystemAccess();
        if (!result.success || !result.status) throw new Error(result.error || "Permission setup failed.");
        renderSystemAccess(result.status);
        setSectionFeedback(
          "access-feedback",
          result.needsManual?.length
            ? `Saved. Finish the highlighted items in ${platformPresentation().privacyButton}.`
            : "One-time permission setup saved.",
        );
      }
      permissionOnlyCompleted = isPermissionOnlySetup;
    }
    if (setupStep === 3) {
      await savePreferences();
      setSectionFeedback("preferences-feedback", "Preferences saved.");
    }
  } catch (error) {
    const feedback = setupStep === 0
      ? "settings-feedback"
      : setupStep === 1
        ? "voice-feedback"
        : setupStep === 2
          ? "access-feedback"
          : "preferences-feedback";
    setSectionFeedback(feedback, error instanceof Error ? error.message : "Could not save this setup step.", true);
    return;
  } finally {
    if (nextButton) nextButton.disabled = false;
  }
  if (permissionOnlyCompleted) {
    isFirstTimeSetup = false;
    isPermissionOnlySetup = false;
    const welcome = document.getElementById("settings-welcome");
    if (welcome) welcome.style.display = "none";
    const nav = document.getElementById("setup-nav");
    if (nav) nav.style.display = "none";
    const sectionNav = document.getElementById("settings-section-nav");
    if (sectionNav) sectionNav.style.display = "";
    closeSettings();
    return;
  }
  setupStep++;
  if (setupStep >= 4) {
    // Done — save everything and close
    isFirstTimeSetup = false;
    localStorage.setItem("jarvis_setup_dismissed", "1");
    const welcome = document.getElementById("settings-welcome");
    if (welcome) welcome.style.display = "none";
    const nav = document.getElementById("setup-nav");
    if (nav) nav.style.display = "none";
    const sectionNav = document.getElementById("settings-section-nav");
    if (sectionNav) sectionNav.style.display = "";

    showSettingsPage(activeSettingsPage);

    closeSettings();
    return;
  }
  showSetupStep(setupStep);
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export async function openSettings(knownStatus?: StatusResponse) {
  if (isOpen) return;
  isOpen = true;

  if (!panelEl) {
    panelEl = createPanel();
    configurePlatformPresentation();
    wireEvents();
    const desktop = getDesktopBridge();
    const installButton = document.getElementById("btn-install-voice-pack") as HTMLButtonElement | null;
    if (!desktop && installButton) installButton.disabled = true;
  }

  isFirstTimeSetup = false;
  showSettingsPage(activeSettingsPage);
  panelEl.style.display = "block";
  // Trigger the transition reliably even when Chromium throttles animation
  // frames while the desktop window is still becoming visible.
  void panelEl.offsetWidth;
  panelEl.classList.add("open");

  // Load data
  // Even when the caller already checked readiness, render a fresh status into
  // every field. The first-run path previously reused data without applying it,
  // leaving the Ollama card hidden and stale cloud-key controls visible.
  const status = await loadStatus() ?? knownStatus;
  await loadPreferences();
  await loadSecretStorageStatus();
  const access = await loadSystemAccess(false);
  await loadDiagnostics();

  // Check for first-time setup
  if (access && !access.setup?.completed) {
    enterPermissionSetupMode();
  } else if (status && !status.llm_ready && localStorage.getItem("jarvis_setup_dismissed") !== "1") {
    enterSetupMode();
  }
}

export function closeSettings() {
  if (!panelEl || !isOpen) return;
  isOpen = false;
  panelEl.classList.remove("open");
  setTimeout(() => {
    if (panelEl) panelEl.style.display = "none";
  }, 300);
}

export function isSettingsOpen(): boolean {
  return isOpen;
}

/**
 * Check if first-time setup is needed and auto-open.
 */
export async function checkFirstTimeSetup(): Promise<boolean> {
  try {
    const desktop = getDesktopBridge();
    if (desktop) {
      const access = await desktop.getSystemAccess({ probeAutomation: false });
      if (!access.setup?.completed) {
        await openSettings();
        return true;
      }
    }
    const status = await apiGet<StatusResponse>("/api/settings/status");
    if (!status.llm_ready && localStorage.getItem("jarvis_setup_dismissed") !== "1") {
      await openSettings(status);
      return true;
    }
  } catch {
    // Server not ready yet, skip
  }
  return false;
}
