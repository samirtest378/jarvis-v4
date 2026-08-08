import assert from "node:assert/strict";
import { readFileSync, statSync } from "node:fs";
import { dirname, join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontend = join(dirname(fileURLToPath(import.meta.url)), "..");
const html = readFileSync(join(frontend, "index.html"), "utf8");
const settings = readFileSync(join(frontend, "src", "settings.ts"), "utf8");
const main = readFileSync(join(frontend, "src", "main.ts"), "utf8");
const orb = readFileSync(join(frontend, "src", "orb.ts"), "utf8");
const style = readFileSync(join(frontend, "src", "style.css"), "utf8");

const states = ["idle", "listening", "thinking", "speaking"];

test("the product surface includes one recorded clip for every assistant state", () => {
  for (const state of states) {
    assert.match(html, new RegExp(`data-state="${state}"[^>]+orb-${state}\\.mp4`));
    const video = join(frontend, "public", "assets", `orb-${state}.mp4`);
    assert.ok(statSync(video).size > 1_000_000, `${state} recording is unexpectedly small`);
    assert.equal(readFileSync(video).subarray(4, 8).toString("ascii"), "ftyp");
  }
});

test("the uninterrupted live animation is the recommended default", () => {
  assert.match(settings, /value="live">Smooth Live — continuous and audio-reactive \(recommended\)/);
  assert.match(settings, /value="video">Recorded 4K — low power/);
  assert.match(main, /jarvis_smooth_orb_migration_v1/);
  assert.match(main, /storedOrbStyle = "live"/);
  assert.equal((html.match(/data-loop-start="2"/g) || []).length, 3);
});

test("the visible particle mesh and fallback crossfade are smooth", () => {
  assert.match(orb, /const LINE_REBUILD_INTERVAL = 1/);
  assert.match(orb, /frameAccumulatorMs/);
  assert.match(orb, /const audioEase = 1 - decay/);
  assert.match(style, /opacity 320ms cubic-bezier\(0\.22, 1, 0\.36, 1\)/);
});

test("the Windows live renderer protects integrated graphics without video cuts", () => {
  assert.match(main, /document\.documentElement\.dataset\.platform = getRuntimeConfig\(\)\.platform/);
  assert.match(orb, /const N = isWindows \? 1200 : 2000/);
  assert.match(orb, /const pixelRatioCap = isWindows \? 1\.1 : 2/);
  assert.match(orb, /const MAX_LINES = isWindows \? 3600 : 8000/);
  assert.match(orb, /enabled \? 30 : 45/);
  assert.doesNotMatch(orb, /disableHardwareAcceleration/);
});
