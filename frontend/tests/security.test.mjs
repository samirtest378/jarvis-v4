import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const testDir = path.dirname(fileURLToPath(import.meta.url));
const source = fs.readFileSync(path.resolve(testDir, "../src/runtime.ts"), "utf8");

test("browser token is tab-scoped, validated, and removed from the address bar", () => {
  assert.match(source, /sessionStorage\.getItem\("jarvis_auth_token"\)/);
  assert.match(source, /sessionStorage\.setItem\("jarvis_auth_token", queryToken\)/);
  assert.match(source, /\^\[A-Za-z0-9_-\]\{32,256\}\$/);
  assert.match(source, /localStorage\.removeItem\("jarvis_auth_token"\)/);
  assert.match(source, /history\.replaceState\(null, "", window\.location\.pathname\)/);
  assert.doesNotMatch(source, /localStorage\.setItem\("jarvis_auth_token"/);
});
