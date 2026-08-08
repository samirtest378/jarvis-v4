"use strict";

/**
 * Secret parsing and environment/keychain resolution for the desktop shell.
 *
 * This module deliberately has no Electron dependency so the credential
 * boundary can be tested without starting the application. Values are only
 * ever returned to the main process; the renderer receives presence flags.
 */

const SECRET_DEFINITIONS = Object.freeze([
  Object.freeze({ output: "openaiApiKey", store: "openaiApiKey", env: Object.freeze(["OPENAI_API_KEY"]) }),
  Object.freeze({ output: "anthropicApiKey", store: "anthropicApiKey", env: Object.freeze(["ANTHROPIC_API_KEY"]) }),
  Object.freeze({ output: "moonshotApiKey", store: "moonshotApiKey", env: Object.freeze(["MOONSHOT_API_KEY", "KIMI_API_KEY"]) }),
  Object.freeze({ output: "dashscopeApiKey", store: "dashscopeApiKey", env: Object.freeze(["DASHSCOPE_API_KEY", "QWEN_API_KEY"]) }),
  Object.freeze({ output: "geminiApiKey", store: "geminiApiKey", env: Object.freeze(["GEMINI_API_KEY", "GOOGLE_API_KEY"]) }),
  Object.freeze({ output: "xaiApiKey", store: "xaiApiKey", env: Object.freeze(["XAI_API_KEY", "GROK_API_KEY"]) }),
  Object.freeze({ output: "openaiCompatibleApiKey", store: "openaiCompatibleApiKey", env: Object.freeze(["OPENAI_COMPATIBLE_API_KEY"]) }),
  Object.freeze({ output: "fishApiKey", store: "fishApiKey", env: Object.freeze(["FISH_API_KEY"]) }),
  Object.freeze({ output: "googleOauthClientId", store: "googleOauthClientId", env: Object.freeze(["GOOGLE_OAUTH_CLIENT_ID"]) }),
  Object.freeze({ output: "googleOauthClientSecret", store: "googleOauthClientSecret", env: Object.freeze(["GOOGLE_OAUTH_CLIENT_SECRET"]) }),
  Object.freeze({ output: "googleRefreshToken", store: "googleRefreshToken", env: Object.freeze(["GOOGLE_REFRESH_TOKEN"]) }),
]);

const KNOWN_KEY_VARIABLES = new Set(SECRET_DEFINITIONS.flatMap((definition) => definition.env));

function stripMatchingQuotes(value) {
  let result = value.trim();
  for (let count = 0; count < 2; count++) {
    if (result.length < 2) break;
    const first = result[0];
    if ((first !== "\"" && first !== "'") || result[result.length - 1] !== first) break;
    result = result.slice(1, -1).trim();
  }
  return result;
}

function meaningfulSecret(value) {
  let cleaned = typeof value === "string" ? value.trim() : "";
  if (!cleaned || /[\r\n\0]/.test(cleaned)) return "";

  cleaned = stripMatchingQuotes(cleaned);

  // People commonly paste the whole line copied from a provider setup guide.
  // Only unwrap recognized key variables so a token containing '=' remains
  // byte-for-byte intact.
  const assignment = cleaned.match(/^(?:export\s+)?([A-Z][A-Z0-9_]*)\s*=\s*([\s\S]*)$/i);
  if (assignment && KNOWN_KEY_VARIABLES.has(assignment[1].toUpperCase())) {
    cleaned = stripMatchingQuotes(assignment[2]);
  }

  cleaned = cleaned.replace(/^authorization\s*:\s*/i, "").trim();
  if (/^bearer\s+/i.test(cleaned)) cleaned = cleaned.slice(cleaned.search(/\s/) + 1).trim();
  cleaned = stripMatchingQuotes(cleaned);

  if (!cleaned || /[\r\n\0]/.test(cleaned)) return "";
  if (/^your-[a-z0-9-]+-api-key-here$/i.test(cleaned) || /^(?:changeme|replace-me)$/i.test(cleaned)) return "";
  return cleaned;
}

function normalizeStorageMode(value) {
  return String(value || "").trim().toLowerCase() === "local" ? "local" : "keychain";
}

function resolveSecrets(environment, encryptedStore, decrypt) {
  const result = {};
  const env = environment && typeof environment === "object" ? environment : {};
  const store = encryptedStore && typeof encryptedStore === "object" ? encryptedStore : {};
  const decryptValue = typeof decrypt === "function" ? decrypt : () => "";

  for (const definition of SECRET_DEFINITIONS) {
    // An explicit in-app save must replace a stale inherited environment
    // value; otherwise the Settings test succeeds with the newly pasted key
    // but the restarted backend silently goes back to the old one. Managed
    // environment-only installs continue to work when no saved key exists.
    let value = meaningfulSecret(decryptValue(store[definition.store]));
    if (!value) {
      for (const envName of definition.env) {
        value = meaningfulSecret(env[envName]);
        if (value) break;
      }
    }
    result[definition.output] = value;
  }
  return result;
}

function resolveSecretsForMode({ mode, environment, encryptedStore, localStore, decrypt }) {
  if (normalizeStorageMode(mode) === "local") {
    // Never call the operating-system decryptor in password-free mode. On
    // macOS, even attempting decryption can display a Keychain password box.
    return resolveSecrets(environment, localStore, (value) => value);
  }
  return resolveSecrets(environment, encryptedStore, decrypt);
}

/**
 * Remove credentials from a child process environment and prepare a one-shot
 * stdin payload instead. Process environments are observable to other
 * same-user processes on several desktop platforms; a pipe is not.
 */
function buildBackendSecretTransfer(environment, resolvedSecrets, additionalSecrets = {}) {
  const childEnvironment = { ...(environment || {}) };
  const runtimeSecrets = {};

  for (const definition of SECRET_DEFINITIONS) {
    for (const envName of definition.env) delete childEnvironment[envName];
    const value = meaningfulSecret(resolvedSecrets?.[definition.output]);
    if (value) runtimeSecrets[definition.env[0]] = value;
  }
  for (const [name, rawValue] of Object.entries(additionalSecrets || {})) {
    const value = meaningfulSecret(rawValue);
    if (/^[A-Z][A-Z0-9_]{1,80}$/.test(name) && value) runtimeSecrets[name] = value;
  }
  childEnvironment.JARVIS_RUNTIME_SECRETS_STDIN = "1";
  return { childEnvironment, runtimeSecrets };
}

module.exports = {
  SECRET_DEFINITIONS,
  buildBackendSecretTransfer,
  meaningfulSecret,
  normalizeStorageMode,
  resolveSecrets,
  resolveSecretsForMode,
};
