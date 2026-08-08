"use strict";

const assert = require("node:assert/strict");
const test = require("node:test");

const {
  GOOGLE_SCOPES,
  buildAuthorizationUrl,
  createPkce,
  exchangeAuthorizationCode,
  validateClientId,
} = require("../google_oauth.cjs");

const CLIENT_ID = "123456789-example.apps.googleusercontent.com";

test("Google desktop authorization uses PKCE, state, offline access, and the narrowest scopes", () => {
  const pkce = createPkce();
  const url = new URL(buildAuthorizationUrl({
    clientId: CLIENT_ID,
    redirectUri: "http://127.0.0.1:54321",
    challenge: pkce.challenge,
    state: pkce.state,
  }));

  assert.equal(url.origin, "https://accounts.google.com");
  assert.equal(url.searchParams.get("code_challenge_method"), "S256");
  assert.equal(url.searchParams.get("code_challenge"), pkce.challenge);
  assert.equal(url.searchParams.get("state"), pkce.state);
  assert.equal(url.searchParams.get("access_type"), "offline");
  assert.equal(url.searchParams.get("prompt"), "consent");
  assert.deepEqual(url.searchParams.get("scope").split(" "), [...GOOGLE_SCOPES]);

  // Sending is requested, because the user asked JARVIS to send mail, and
  // `gmail.send` cannot read a mailbox — it only submits new messages. What
  // must stay out are the scopes that can rewrite or destroy what is already
  // there, which the user would never see happen.
  assert.ok(GOOGLE_SCOPES.includes("https://www.googleapis.com/auth/gmail.send"));
  assert.ok(GOOGLE_SCOPES.every((scope) => !/\.modify|mail\.google\.com|calendar$/.test(scope)));
  assert.ok(GOOGLE_SCOPES.every((scope) => !/gmail\.readonly|calendar\.events$/.test(scope)));
});

test("Google client IDs are validated before a browser is opened", () => {
  assert.equal(validateClientId(CLIENT_ID), CLIENT_ID);
  for (const invalid of ["", "client.example.com", "bad\n.apps.googleusercontent.com", "https://example.com/"]) {
    assert.throws(() => validateClientId(invalid), /valid Google Desktop OAuth client ID/);
  }
});

test("authorization-code exchange never returns the access token to callers", async () => {
  let request;
  const result = await exchangeAuthorizationCode({
    clientId: CLIENT_ID,
    clientSecret: "desktop-secret",
    redirectUri: "http://127.0.0.1:54321",
    code: "one-time-code",
    verifier: createPkce().verifier,
    fetchImpl: async (url, options) => {
      request = { url, options };
      return { ok: true, json: async () => ({ access_token: "never-exposed", refresh_token: "refresh-value" }) };
    },
  });

  assert.deepEqual(result, { refreshToken: "refresh-value" });
  assert.equal(request.url, "https://oauth2.googleapis.com/token");
  assert.match(request.options.body, /grant_type=authorization_code/);
  assert.match(request.options.body, /code_verifier=/);
});
