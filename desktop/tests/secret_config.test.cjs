"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  buildBackendSecretTransfer,
  meaningfulSecret,
  normalizeStorageMode,
  resolveSecrets,
  resolveSecretsForMode,
} = require("../secret_config.cjs");

test("backend credentials use a one-shot pipe instead of process environment", () => {
  const { childEnvironment, runtimeSecrets } = buildBackendSecretTransfer(
    {
      PATH: "/usr/bin",
      OPENAI_API_KEY: "stale-openai-key",
      GOOGLE_REFRESH_TOKEN: "stale-refresh-token",
    },
    {
      openaiApiKey: "saved-openai-key",
      googleRefreshToken: "saved-refresh-token",
    },
    { JARVIS_AUTH_TOKEN: "ephemeral-session-token" },
  );

  assert.equal(childEnvironment.PATH, "/usr/bin");
  assert.equal(childEnvironment.JARVIS_RUNTIME_SECRETS_STDIN, "1");
  assert.equal("OPENAI_API_KEY" in childEnvironment, false);
  assert.equal("GOOGLE_REFRESH_TOKEN" in childEnvironment, false);
  assert.deepEqual(runtimeSecrets, {
    OPENAI_API_KEY: "saved-openai-key",
    GOOGLE_REFRESH_TOKEN: "saved-refresh-token",
    JARVIS_AUTH_TOKEN: "ephemeral-session-token",
  });
});

test("normalizes common API-key paste formats without changing the token", () => {
  const expected = "sk-example==";
  for (const value of [
    " sk-example== ",
    "\"sk-example==\"",
    "Bearer sk-example==",
    "Authorization: Bearer sk-example==",
    "export ANTHROPIC_API_KEY='sk-example=='",
    "QWEN_API_KEY=\"sk-example==\"",
  ]) {
    assert.equal(meaningfulSecret(value), expected);
  }
});

test("rejects placeholders and multi-line values", () => {
  assert.equal(meaningfulSecret("your-anthropic-api-key-here"), "");
  assert.equal(meaningfulSecret("replace-me"), "");
  assert.equal(meaningfulSecret("first\nsecond"), "");
});

test("resolves canonical and conventional provider aliases", () => {
  const secrets = resolveSecrets({
    KIMI_API_KEY: "Bearer kimi-value",
    QWEN_API_KEY: "qwen-value",
    GOOGLE_API_KEY: "gemini-value",
    GROK_API_KEY: "grok-value",
    OPENAI_API_KEY: "openai-value",
    OPENAI_COMPATIBLE_API_KEY: "custom-value",
  }, {}, () => "");

  assert.equal(secrets.openaiApiKey, "openai-value");
  assert.equal(secrets.moonshotApiKey, "kimi-value");
  assert.equal(secrets.dashscopeApiKey, "qwen-value");
  assert.equal(secrets.geminiApiKey, "gemini-value");
  assert.equal(secrets.xaiApiKey, "grok-value");
  assert.equal(secrets.openaiCompatibleApiKey, "custom-value");
});

test("Google account credentials stay inside the main-process secret boundary", () => {
  const secrets = resolveSecrets({
    GOOGLE_OAUTH_CLIENT_ID: "123-example.apps.googleusercontent.com",
    GOOGLE_OAUTH_CLIENT_SECRET: "desktop-secret",
    GOOGLE_REFRESH_TOKEN: "refresh-token",
  }, {}, () => "");

  assert.equal(secrets.googleOauthClientId, "123-example.apps.googleusercontent.com");
  assert.equal(secrets.googleOauthClientSecret, "desktop-secret");
  assert.equal(secrets.googleRefreshToken, "refresh-token");
});

test("an explicit keychain save wins while environment remains a fallback", () => {
  const environment = {
    MOONSHOT_API_KEY: "canonical-value",
    KIMI_API_KEY: "alias-value",
  };
  const store = { moonshotApiKey: "encrypted-value" };
  assert.equal(resolveSecrets(environment, store, (value) => value).moonshotApiKey, "encrypted-value");

  delete store.moonshotApiKey;
  environment.MOONSHOT_API_KEY = "your-moonshot-api-key-here";
  assert.equal(resolveSecrets(environment, store, (value) => value).moonshotApiKey, "alias-value");

  delete environment.KIMI_API_KEY;
  assert.equal(resolveSecrets(environment, store, (value) => value).moonshotApiKey, "");
});

test("password-free local mode never calls the Keychain decryptor", () => {
  let decryptCalls = 0;
  const result = resolveSecretsForMode({
    mode: "local",
    environment: { ANTHROPIC_API_KEY: "stale-environment-value" },
    encryptedStore: { anthropicApiKey: "encrypted-keychain-value" },
    localStore: { anthropicApiKey: "local-password-free-value" },
    decrypt: () => {
      decryptCalls += 1;
      throw new Error("Keychain must not be opened");
    },
  });

  assert.equal(result.anthropicApiKey, "local-password-free-value");
  assert.equal(decryptCalls, 0);
});

test("storage mode accepts only the explicit password-free value", () => {
  assert.equal(normalizeStorageMode("local"), "local");
  assert.equal(normalizeStorageMode(" LOCAL "), "local");
  assert.equal(normalizeStorageMode("keychain"), "keychain");
  assert.equal(normalizeStorageMode("unknown"), "keychain");
});
