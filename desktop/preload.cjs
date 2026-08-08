const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("jarvisDesktop", Object.freeze({
  getRuntimeConfig: () => ipcRenderer.sendSync("runtime:get"),
  getSecretStorageStatus: () => ipcRenderer.invoke("secrets:status"),
  activateSecretStorage: (mode) => ipcRenderer.invoke("secrets:activate-storage", mode),
  saveSecrets: (values) => ipcRenderer.invoke("secrets:save", values),
  restartBackend: () => ipcRenderer.invoke("backend:restart"),
  deleteAllLocalData: () => ipcRenderer.invoke("privacy:delete-all-data"),
  getSystemAccess: (options) => ipcRenderer.invoke("permissions:status", options),
  requestMicrophoneAccess: () => ipcRenderer.invoke("permissions:request-microphone"),
  requestAllSystemAccess: () => ipcRenderer.invoke("permissions:request-all"),
  openPrivacySettings: (kind) => ipcRenderer.invoke("permissions:open-settings", kind),
  connectGoogle: (values) => ipcRenderer.invoke("google:connect", values),
  disconnectGoogle: () => ipcRenderer.invoke("google:disconnect"),
  getVoicePackStatus: () => ipcRenderer.invoke("voice-pack:status"),
  installVoicePack: () => ipcRenderer.invoke("voice-pack:install"),
  getDiagnostics: () => ipcRenderer.invoke("support:diagnostics"),
  exportDiagnostics: () => ipcRenderer.invoke("support:export-diagnostics"),
  setVoiceActivity: (active) => ipcRenderer.invoke("performance:set-voice-active", active === true),
  onOpenSettings: (callback) => ipcRenderer.on("ui:open-settings", () => callback()),
}));
