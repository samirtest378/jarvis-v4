/** Record the real orb animation to video, one state per clip.
 *
 * Development tool, not part of the app. The shipped animation is a video so
 * that playback costs almost nothing, but it has to be the *actual* animation
 * rather than a reimplementation — so this page drives `createOrb` itself and
 * captures what it draws at a true 4K-wide 3840×2400. The 16:10 aspect ratio
 * matches the application window, so the orb is not stretched or cropped.
 *
 * Frames are stepped manually: a background window throttles
 * `requestAnimationFrame` to a standstill, and even in the foreground the
 * recorder must not depend on the machine keeping up in real time. Every frame
 * is rendered, handed to the capture stream explicitly, and only then does the
 * clock advance — so the result is exact regardless of how fast this runs.
 *
 * Usage: start the dev server, open /record.html, and let it finish. Each clip
 * is POSTed to the collector (scripts/record_orb_clips.py) which writes it to
 * disk and converts it to MP4.
 */

import { createOrb, type Orb, type OrbState } from "./orb";

const COLLECTOR = "http://127.0.0.1:5175";
const FPS = 60;

/** Window size to simulate, in CSS pixels.
 *
 * This is not the output resolution — the recorder uses a device pixel ratio
 * of 2, so the captured frames come out at 3840×2400. Recording at a larger
 * *logical* size instead would shrink every particle relative to the frame:
 * point size scales with the viewport, so the same artwork rendered into a
 * huge canvas becomes a field of sub-pixel specks that average away to almost
 * nothing once the video is scaled back down to a real window. */
const WINDOW_WIDTH = 1920;
const WINDOW_HEIGHT = 1200;

/** Clips in the order a real exchange runs through them.
 *
 * `from` is the state the orb sits in before capture starts, so each clip
 * opens on the genuine transition into its own state — the tumble and the
 * change of radius that the live animation plays. Recording each state in
 * isolation (the first attempt) produced clips that only held steady poses, so
 * switching between them looked like a cut instead of a move.
 *
 * Idle needs no `from`: it is the resting loop, and it is the one clip that
 * gets a seamless join afterwards because it is on screen almost always. */
const CLIPS: { state: OrbState; from?: OrbState; seconds: number }[] = [
  { state: "idle", seconds: 8 },
  { state: "listening", from: "idle", seconds: 5 },
  { state: "thinking", from: "listening", seconds: 6 },
  { state: "speaking", from: "thinking", seconds: 6 },
];

const logEl = document.getElementById("log") as HTMLDivElement;
const canvas = document.getElementById("orb-canvas") as HTMLCanvasElement;


function log(message: string) {
  logEl.textContent = message;
  console.log("[recorder]", message);
}

/** A fake analyser so "speaking" pulses the way it does with real audio.
 *  The live orb reads bass and mid bands from getByteFrequencyData; feeding it
 *  a gentle periodic signal reproduces that motion deterministically. */
function createFakeAnalyser(): AnalyserNode {
  let frame = 0;
  const bins = 64;
  return {
    frequencyBinCount: bins,
    getByteFrequencyData(target: Uint8Array) {
      frame += 1;
      const t = frame / FPS;
      // Speech-like envelope: a slow phrase rhythm with faster syllables.
      const envelope = Math.max(0, Math.sin(t * 2.1)) * (0.55 + 0.45 * Math.sin(t * 7.3));
      for (let i = 0; i < bins; i++) {
        const band = i < 8 ? 1.0 : i < 24 ? 0.75 : 0.25;
        target[i] = Math.min(255, Math.max(0, envelope * band * 210));
      }
    },
  } as unknown as AnalyserNode;
}

function toPng(source: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    source.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("canvas produced no image"))),
      "image/png",
    );
  });
}

async function recordClip(
  orb: Orb,
  state: OrbState,
  seconds: number,
  from?: OrbState,
): Promise<void> {
  const totalFrames = Math.round(seconds * FPS);

  const reset = await fetch(`${COLLECTOR}/reset/${state}`, { method: "POST" });
  if (!reset.ok) throw new Error(`collector could not reset ${state}: ${reset.status}`);

  // Settle into the previous state first, then switch — so frame zero of the
  // capture is the moment the transition begins.
  orb.setState(from ?? state);
  for (let warm = 0; warm < 240; warm++) orb.step?.(1, warm / FPS);
  orb.setState(state);

  for (let i = 0; i < totalFrames; i++) {
    orb.step?.(1, i / FPS);
    const frame = await toPng(canvas);
    // Awaiting the upload is deliberate backpressure. Handing frames to an
    // encoder as fast as they render buried the main thread; here the page
    // simply runs at whatever speed the collector can absorb.
    // Sent as text/plain so the request stays a "simple" cross-origin POST and
    // skips the preflight round trip on every single frame.
    const response = await fetch(`${COLLECTOR}/frame/${state}/${String(i).padStart(5, "0")}`, {
      method: "POST",
      body: new Blob([frame], { type: "text/plain" }),
    });
    if (!response.ok) throw new Error(`collector rejected ${state} frame ${i}: ${response.status}`);
    if (i % 30 === 0) log(`${state}: frame ${i}/${totalFrames}`);
  }

  log(`${state}: encoding…`);
  const encoded = await fetch(`${COLLECTOR}/encode/${state}`, { method: "POST" });
  if (!encoded.ok) throw new Error(`encoding ${state} failed: ${encoded.status}`);
}

async function main() {
  // The orb sizes itself from the window, so present it with the window we
  // want it to draw for. It applies its own device pixel ratio on top.
  Object.defineProperty(window, "innerWidth", { value: WINDOW_WIDTH, configurable: true });
  Object.defineProperty(window, "innerHeight", { value: WINDOW_HEIGHT, configurable: true });
  Object.defineProperty(window, "devicePixelRatio", { value: 2, configurable: true });

  const orb = createOrb(canvas);
  orb.detachLoop?.();
  orb.setAnalyser(createFakeAnalyser());
  log(`4K recorder ready: ${canvas.width}×${canvas.height}`);

  for (const clip of CLIPS) {
    log(`recording ${clip.state}…`);
    await recordClip(orb, clip.state, clip.seconds, clip.from);
  }

  await fetch(`${COLLECTOR}/done`, { method: "POST" });
  log("all clips recorded — you can close this page");
}

void main().catch((error) => {
  log(`failed: ${error?.message || error}`);
  console.error(error);
});
