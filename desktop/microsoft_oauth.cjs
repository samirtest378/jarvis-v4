"use strict";

const crypto = require("node:crypto");

const AUTHORIZATION_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize";
const TOKEN_ENDPOINT = "https://login.microsoftonline.com/common/oauth2/v2.0/token";
// Mail and Calendar match the private data JARVIS can already use through
// Apple apps and classic Outlook. Mail.Send is exercised only after an
// explicit user instruction; no delete or mailbox-modification scope exists.
const MICROSOFT_SCOPES = Object.freeze([
  "openid",
  "profile",
  "email",
  "offline_access",
  "https://graph.microsoft.com/Mail.Read",
  "https://graph.microsoft.com/Mail.Send",
  "https://graph.microsoft.com/Calendars.Read",
]);

function cleanOAuthValue(value, maxLength = 2048) {
  const original = typeof value === "string" ? value : "";
  // Reject controls before trimming. Otherwise a pasted newline at either
  // edge disappears and an unsafe multi-line value is accepted as valid.
  if (/[\r\n\0]/.test(original)) return "";
  const result = original.trim();
  if (!result || result.length > maxLength) return "";
  return result;
}

function validateClientId(value) {
  const clientId = cleanOAuthValue(value, 64);
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(clientId)) {
    throw new Error("Enter a valid Microsoft desktop application client ID.");
  }
  return clientId;
}

function createPkce() {
  const verifier = crypto.randomBytes(64).toString("base64url");
  const challenge = crypto.createHash("sha256").update(verifier, "ascii").digest("base64url");
  const state = crypto.randomBytes(32).toString("base64url");
  return { verifier, challenge, state };
}

function buildAuthorizationUrl({ clientId, redirectUri, challenge, state }) {
  const url = new URL(AUTHORIZATION_ENDPOINT);
  url.search = new URLSearchParams({
    client_id: validateClientId(clientId),
    redirect_uri: cleanOAuthValue(redirectUri, 1024),
    response_type: "code",
    response_mode: "query",
    scope: MICROSOFT_SCOPES.join(" "),
    prompt: "select_account",
    code_challenge: cleanOAuthValue(challenge, 256),
    code_challenge_method: "S256",
    state: cleanOAuthValue(state, 256),
  }).toString();
  return url.toString();
}

async function exchangeAuthorizationCode({ clientId, redirectUri, code, verifier, fetchImpl = fetch }) {
  const form = new URLSearchParams({
    client_id: validateClientId(clientId),
    redirect_uri: cleanOAuthValue(redirectUri, 1024),
    code: cleanOAuthValue(code, 4096),
    code_verifier: cleanOAuthValue(verifier, 256),
    scope: MICROSOFT_SCOPES.join(" "),
    grant_type: "authorization_code",
  });
  const response = await fetchImpl(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
    signal: AbortSignal.timeout(15000),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error("Microsoft did not complete the account connection.");
  const refreshToken = cleanOAuthValue(payload.refresh_token, 16384);
  if (!refreshToken) throw new Error("Microsoft did not return an offline refresh token. Reconnect and approve offline access.");
  return { refreshToken };
}

module.exports = {
  AUTHORIZATION_ENDPOINT,
  MICROSOFT_SCOPES,
  TOKEN_ENDPOINT,
  buildAuthorizationUrl,
  cleanOAuthValue,
  createPkce,
  exchangeAuthorizationCode,
  validateClientId,
};
