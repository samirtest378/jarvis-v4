"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  MICROSOFT_SCOPES,
  buildAuthorizationUrl,
  createPkce,
  exchangeAuthorizationCode,
  validateClientId,
} = require("../microsoft_oauth.cjs");

const CLIENT_ID = "4f3e2d1c-0b9a-48f7-86e5-123456789abc";

test("Microsoft desktop authorization uses PKCE, offline access, and no client secret", () => {
  const pkce = createPkce();
  const url = new URL(buildAuthorizationUrl({
    clientId: CLIENT_ID,
    redirectUri: "http://localhost:54321",
    challenge: pkce.challenge,
    state: pkce.state,
  }));

  assert.equal(url.origin, "https://login.microsoftonline.com");
  assert.equal(url.pathname, "/common/oauth2/v2.0/authorize");
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.equal(url.searchParams.get("code_challenge"), pkce.challenge);
  assert.equal(url.searchParams.get("state"), pkce.state);
  assert.deepEqual(url.searchParams.get("scope").split(" "), [...MICROSOFT_SCOPES]);
  assert.ok(MICROSOFT_SCOPES.includes("offline_access"));
  assert.ok(MICROSOFT_SCOPES.includes("https://graph.microsoft.com/Mail.Send"));
  assert.ok(MICROSOFT_SCOPES.every((scope) => !/Mail\.ReadWrite|Calendars\.ReadWrite|\.All$/.test(scope)));
});

test("Microsoft application IDs are validated before browser authorization", () => {
  assert.equal(validateClientId(CLIENT_ID), CLIENT_ID);
  for (const invalid of ["", "not-a-guid", `${CLIENT_ID}\n`, "https://login.microsoftonline.com/"]) {
    assert.throws(() => validateClientId(invalid), /valid Microsoft desktop application client ID/);
  }
});

test("Microsoft code exchange is public-client PKCE and returns only the refresh token", async () => {
  let request;
  const result = await exchangeAuthorizationCode({
    clientId: CLIENT_ID,
    redirectUri: "http://localhost:54321",
    code: "one-time-code",
    verifier: createPkce().verifier,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({ access_token: "never-exposed", refresh_token: "refresh-value" }) };
    },
  });

  assert.deepEqual(result, { refreshToken: "refresh-value" });
  assert.equal(request.url, "https://login.microsoftonline.com/common/oauth2/v2.0/token");
  assert.match(request.options.body, /grant_type=authorization_code/);
  assert.match(request.options.body, /code_verifier=/);
  assert.doesNotMatch(request.options.body, /client_secret/);
});
