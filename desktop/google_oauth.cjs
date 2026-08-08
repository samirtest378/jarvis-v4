"use strict";

const crypto = require("node:crypto");

const AUTHORIZATION_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth";
const TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token";
const REVOCATION_ENDPOINT = "https://oauth2.googleapis.com/revoke";
// Calendar stays read-only. Gmail is metadata plus send — `gmail.send` cannot
// read anything, it only submits new messages, and everything it sends is
// visible to the user in Sent.
const GOOGLE_SCOPES = Object.freeze([
  "openid",
  "email",
  "https://www.googleapis.com/auth/gmail.metadata",
  "https://www.googleapis.com/auth/gmail.send",
  "https://www.googleapis.com/auth/calendar.events.readonly",
]);

function cleanOAuthValue(value, maxLength = 2048) {
  const result = typeof value === "string" ? value.trim() : "";
  if (!result || result.length > maxLength || /[\r\n\0]/.test(result)) return "";
  return result;
}

function validateClientId(value) {
  const clientId = cleanOAuthValue(value, 512);
  if (!/^[A-Za-z0-9._-]+\.apps\.googleusercontent\.com$/.test(clientId)) {
    throw new Error("Enter a valid Google Desktop OAuth client ID.");
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
    scope: GOOGLE_SCOPES.join(" "),
    access_type: "offline",
    prompt: "consent",
    code_challenge: cleanOAuthValue(challenge, 256),
    code_challenge_method: "S256",
    state: cleanOAuthValue(state, 256),
  }).toString();
  return url.toString();
}

async function exchangeAuthorizationCode({ clientId, clientSecret, redirectUri, code, verifier, fetchImpl = fetch }) {
  const form = new URLSearchParams({
    client_id: validateClientId(clientId),
    redirect_uri: cleanOAuthValue(redirectUri, 1024),
    code: cleanOAuthValue(code, 4096),
    code_verifier: cleanOAuthValue(verifier, 256),
    grant_type: "authorization_code",
  });
  const secret = cleanOAuthValue(clientSecret, 2048);
  if (secret) form.set("client_secret", secret);
  const response = await fetchImpl(TOKEN_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: form.toString(),
    signal: AbortSignal.timeout(15000),
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error("Google did not complete the account connection.");
  const refreshToken = cleanOAuthValue(payload.refresh_token, 8192);
  if (!refreshToken) throw new Error("Google did not return an offline refresh token. Remove the old app grant and try again.");
  return { refreshToken };
}

async function revokeToken(token, fetchImpl = fetch) {
  const value = cleanOAuthValue(token, 8192);
  if (!value) return true;
  const response = await fetchImpl(REVOCATION_ENDPOINT, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ token: value }).toString(),
    signal: AbortSignal.timeout(15000),
  });
  return response.ok || response.status === 400;
}

module.exports = {
  AUTHORIZATION_ENDPOINT,
  GOOGLE_SCOPES,
  buildAuthorizationUrl,
  cleanOAuthValue,
  createPkce,
  exchangeAuthorizationCode,
  revokeToken,
  validateClientId,
};
