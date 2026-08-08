export interface RuntimeConfig {
  apiBase: string;
  authToken: string;
  desktop: boolean;
  development: boolean;
  platform: string;
  arch?: string;
  appVersion?: string;
}

export interface SecretSaveResult {
  success: boolean;
  error?: string;
  storageMode?: "keychain" | "local";
  storageBackend?: string;
}

export interface SecretStorageStatus {
  mode: "keychain" | "local";
  requiresPassword: boolean;
  storageBackend: string;
  secureStorageAvailable: boolean;
  hasLocalSecrets?: boolean;
  hasKeychainSecrets?: boolean;
}

export type AccessState = "granted" | "denied" | "restricted" | "not-determined" | "not-granted" | "limited" | "unavailable" | "unknown" | "available" | "managed";

export interface SystemAccessStatus {
  platform: string;
  microphone: AccessState;
  screen: AccessState;
  accessibility: AccessState;
  files: AccessState;
  automation: {
    calendar: AccessState;
    mail: AccessState;
    notes: AccessState;
  };
  setup?: {
    completed: boolean;
    requestedAt: string;
  };
}

export interface DesktopBridge {
  getRuntimeConfig(): RuntimeConfig;
  getSecretStorageStatus(): Promise<SecretStorageStatus>;
  activateSecretStorage(mode: "keychain" | "local"): Promise<SecretSaveResult>;
  saveSecrets(values: {
    storageMode?: "keychain" | "local";
    openaiApiKey?: string;
    anthropicApiKey?: string;
    moonshotApiKey?: string;
    dashscopeApiKey?: string;
    geminiApiKey?: string;
    xaiApiKey?: string;
    openaiCompatibleApiKey?: string;
    fishApiKey?: string;
  }): Promise<SecretSaveResult>;
  restartBackend(): Promise<{ success: boolean; error?: string }>;
  deleteAllLocalData(): Promise<{ success: boolean; canceled?: boolean; error?: string }>;
  getSystemAccess(options?: { probeAutomation?: boolean }): Promise<SystemAccessStatus>;
  requestMicrophoneAccess(): Promise<AccessState>;
  requestAllSystemAccess(): Promise<{
    success: boolean;
    status?: SystemAccessStatus;
    needsManual?: string[];
    settingsOpened?: boolean;
    error?: string;
  }>;
  openPrivacySettings(kind: "all" | "microphone" | "screen" | "automation" | "accessibility" | "files"): Promise<{ success: boolean; error?: string }>;
  connectGoogle(values: { clientId: string; clientSecret?: string; storageMode: "keychain" | "local" }): Promise<{ success: boolean; error?: string; storageMode?: string }>;
  disconnectGoogle(): Promise<{ success: boolean; canceled?: boolean; error?: string }>;
  getVoicePackStatus(): Promise<{
    installed: boolean;
    compatible: boolean;
    name: string;
    version: string;
    platform: string;
    arch: string;
  }>;
  installVoicePack(): Promise<{
    success: boolean;
    canceled?: boolean;
    installed?: boolean;
    name?: string;
    version?: string;
    backupCreated?: boolean;
    error?: string;
  }>;
  getDiagnostics(): Promise<DiagnosticsReport>;
  exportDiagnostics(): Promise<{ success: boolean; canceled?: boolean; fileName?: string; error?: string }>;
  setVoiceActivity(active: boolean): Promise<{ success: boolean }>;
  onOpenSettings(callback: () => void): void;
}

export interface DiagnosticsReport {
  schema: string;
  generated_at: string;
  app: { name: string; version: string; packaged: boolean };
  system: { platform: string; architecture: string; os_version: string };
  local_service: { running: boolean; healthy: boolean; version: string };
  intelligence: { provider: string; configured: boolean; ready?: boolean; provider_key_present: boolean };
  accounts?: { google_connected: boolean };
  voice: {
    active_provider: string;
    offline_pack_installed: boolean;
    recognition_engine?: string;
    recognition_local?: boolean;
  };
  key_storage: { mode: string; protected_by_operating_system: boolean };
  privacy: {
    contains_api_keys: false;
    contains_conversations: false;
    contains_memory_or_tasks: false;
    contains_personal_file_paths: false;
    contains_user_name: false;
  };
}

declare global {
  interface Window {
    jarvisDesktop?: DesktopBridge;
  }
}

function browserRuntime(): RuntimeConfig {
  const candidate = new URLSearchParams(window.location.search).get("token") || "";
  const queryToken = /^[A-Za-z0-9_-]{32,256}$/.test(candidate) ? candidate : "";
  const storedCandidate = sessionStorage.getItem("jarvis_auth_token") || "";
  const storedToken = /^[A-Za-z0-9_-]{32,256}$/.test(storedCandidate) ? storedCandidate : "";
  const authToken = queryToken || storedToken;
  // Remove credentials written by older versions. A browser-mode token now
  // lives only for this tab and is never persisted across browser restarts.
  localStorage.removeItem("jarvis_auth_token");
  if (queryToken) {
    sessionStorage.setItem("jarvis_auth_token", queryToken);
    history.replaceState(null, "", window.location.pathname);
  }
  return {
    apiBase: "",
    authToken,
    desktop: false,
    development: true,
    platform: navigator.platform,
  };
}

const runtime = window.jarvisDesktop?.getRuntimeConfig() ?? browserRuntime();

export function getRuntimeConfig(): RuntimeConfig {
  return runtime;
}

export function getDesktopBridge(): DesktopBridge | undefined {
  return window.jarvisDesktop;
}

export function apiUrl(path: string): string {
  return `${runtime.apiBase}${path}`;
}

export function authHeaders(): Record<string, string> {
  return runtime.authToken
    ? { Authorization: `Bearer ${runtime.authToken}` }
    : {};
}

export function voiceWebSocketUrl(): string {
  const base = runtime.apiBase || window.location.origin;
  const url = new URL("/ws/voice", base);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  return url.toString();
}

export function webSocketProtocols(): string[] {
  return runtime.authToken
    ? ["jarvis-v1", `jarvis-auth.${runtime.authToken}`]
    : ["jarvis-v1"];
}
