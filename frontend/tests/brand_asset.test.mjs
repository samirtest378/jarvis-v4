import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = resolve(fileURLToPath(new URL("..", import.meta.url)));
const html = readFileSync(join(root, "index.html"), "utf8");

test("the top-left JARVIS logo points to a bundled image", () => {
  const source = html.match(/class="brand-logo" src="([^"]+)"/)?.[1];
  assert.ok(source, "brand logo source is required");
  assert.equal(existsSync(join(root, "public", source.replace(/^\//, ""))), true);
});
