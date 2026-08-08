/**
 * JARVIS — Multi-mode particle visualization.
 *
 * Floating particles with line connections between nearby ones.
 * Lines fade in/out based on state. Transition tumble on state change.
 * Speaking pulls particles closer for denser connections.
 */

import * as THREE from "three";

export type OrbState = "idle" | "listening" | "thinking" | "speaking";

export interface Orb {
  setState(s: OrbState): void;
  setAnalyser(a: AnalyserNode | null): void;
  destroy(): void;
  /** Optional: the classic animation does not implement frame pacing. */
  setPowerSaving?(enabled: boolean): void;
  /** Optional: draw one frame on a caller-supplied clock, for recording. */
  step?(k: number, elapsedSeconds: number): void;
  /** Optional: stop the self-driven loop so a recorder owns the timing. */
  detachLoop?(): void;
}

export function createOrb(canvas: HTMLCanvasElement): Orb {
  let destroyed = false;
  const N = 2000;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "low-power" });
  // Full native resolution: the particles are single points, so any downscale
  // softens them visibly. This was capped at 1.5 while the stacked blur layers
  // were making the GPU the bottleneck; with those gone the GPU process sits
  // near idle, so the sharper render is affordable. The cap of 2 keeps a
  // hypothetical 3x display from quadrupling the work for no visible gain.
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);
  renderer.setClearColor(0x050508, 1);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, window.innerWidth / window.innerHeight, 1, 1000);
  camera.position.z = 80;

  // ── Particles ──
  const geo = new THREE.BufferGeometry();
  const pos = new Float32Array(N * 3);
  const vel = new Float32Array(N * 3);
  const phase = new Float32Array(N);

  for (let i = 0; i < N; i++) {
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(2 * Math.random() - 1);
    const r = Math.pow(Math.random(), 0.5) * 25;
    pos[i * 3] = r * Math.sin(phi) * Math.cos(theta);
    pos[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
    pos[i * 3 + 2] = r * Math.cos(phi);
    phase[i] = Math.random() * 1000;
  }

  geo.setAttribute("position", new THREE.BufferAttribute(pos, 3));

  const mat = new THREE.PointsMaterial({
    color: 0x4ca8e8, size: 0.4, transparent: true, opacity: 0.6,
    sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
  });

  const points = new THREE.Points(geo, mat);
  scene.add(points);

  // ── Connection lines ──
  const MAX_LINES = 8000;
  const linePos = new Float32Array(MAX_LINES * 6);
  const lineGeo = new THREE.BufferGeometry();
  lineGeo.setAttribute("position", new THREE.BufferAttribute(linePos, 3));
  lineGeo.setDrawRange(0, 0);

  const lineMat = new THREE.LineBasicMaterial({
    color: 0x4ca8e8, transparent: true, opacity: 0.0,
    blending: THREE.AdditiveBlending, depthWrite: false,
  });

  const lines = new THREE.LineSegments(lineGeo, lineMat);
  scene.add(lines);

  // ── Electrons — bright dots that travel along connections ──
  const MAX_ELECTRONS = 200;
  const electronGeo = new THREE.BufferGeometry();
  const electronPos = new Float32Array(MAX_ELECTRONS * 3);
  electronGeo.setAttribute("position", new THREE.BufferAttribute(electronPos, 3));
  electronGeo.setDrawRange(0, 0);

  const electronMat = new THREE.PointsMaterial({
    color: 0xffffff, size: 0.8, transparent: true, opacity: 1.0,
    sizeAttenuation: true, blending: THREE.AdditiveBlending, depthWrite: false,
  });

  const electrons = new THREE.Points(electronGeo, electronMat);
  scene.add(electrons);

  // Each electron: start point, end point, progress (0-1), speed
  interface Electron { sx: number; sy: number; sz: number; ex: number; ey: number; ez: number; t: number; speed: number; }
  const activeElectrons: Electron[] = [];
  let electronSpawnRate = 0;
  let targetElectronRate = 0;
  let lastElectronSpawn = 0; // timestamp of last spawn

  // Store active connections for electron spawning
  let activeConnections: { x1: number; y1: number; z1: number; x2: number; y2: number; z2: number }[] = [];

  // ── State ──
  let state: OrbState = "idle";
  let targetRadius = 25, currentRadius = 25;
  let targetSpeed = 0.3, currentSpeed = 0.3;
  let targetBright = 0.6, currentBright = 0.6;
  let targetSize = 0.4, currentSize = 0.4;
  let lineAmount = 0, targetLineAmount = 0;
  let lineDistance = 8;

  // Transition tumble
  let spinX = 0, spinY = 0, spinZ = 0;
  let transitionEnergy = 0;
  let lastState: OrbState = "idle";

  // Depth Z
  let cloudZ = 0, cloudZVel = 0;

  // ── Audio ──
  let analyser: AnalyserNode | null = null;
  let freqData = new Uint8Array(64);
  let bass = 0, mid = 0;

  const clock = new THREE.Clock();

  // Reused so the colour lerps below allocate nothing per frame.
  const IDLE_COLOR = new THREE.Color(0x4ca8e8);
  const THINKING_COLOR = new THREE.Color(0x6ec4ff);
  const SPEAKING_COLOR = new THREE.Color(0x5ab8f0);

  let frame = 0;
  // The connection mesh is the visible outline of the globe. Updating it only
  // every third frame made a nominally 60 FPS scene read as 20 FPS, especially
  // during rotation. The spatial grid keeps a per-frame rebuild inexpensive.
  const LINE_REBUILD_INTERVAL = 1;
  let paused = false;

  // Spatial grid for the neighbour search. The cloud is pulled toward a radius
  // of ~28 and the connection range is 8, so a 16-cell axis covers everything
  // it can reach with room to spare; anything further out is clamped into the
  // edge cells, which stays correct because those particles have no neighbours
  // out there anyway. All buffers are allocated once and reused every frame.
  const CELL_AXIS = 16;
  const CELL_TOTAL = CELL_AXIS * CELL_AXIS * CELL_AXIS;
  const GRID_HALF = 48;
  const cellCount = new Int32Array(CELL_TOTAL);
  const cellStart = new Int32Array(CELL_TOTAL);
  const cellFill = new Int32Array(CELL_TOTAL);
  const cellItems = new Int32Array(N);
  const sampleIndex = new Int32Array(N);
  const sampleCell = new Int32Array(N);
  let sampleCount = 0;

  function axisOf(value: number, cellSize: number): number {
    const cell = Math.floor((value + GRID_HALF) / cellSize);
    return cell < 0 ? 0 : cell >= CELL_AXIS ? CELL_AXIS - 1 : cell;
  }

  function cellOf(x: number, y: number, z: number, cellSize: number): number {
    return (axisOf(x, cellSize) * CELL_AXIS + axisOf(y, cellSize)) * CELL_AXIS + axisOf(z, cellSize);
  }

  // Power saving. The animation was written against a 60 Hz frame, so every
  // motion constant below is per-frame. Rendering at 30 Hz would therefore
  // halve the apparent speed — unless each step is scaled by how much time
  // actually passed. `k` is that scale (1.0 at 60 Hz, 2.0 at 30 Hz), which
  // keeps the artwork moving at exactly the same visual speed at any rate.
  const FRAME_60HZ_MS = 1000 / 60;
  let frameBudgetMs = 1000 / 60;
  let lastAnimationTick = performance.now();
  let frameAccumulatorMs = frameBudgetMs;

  // Full rate always. Halving the frame rate is the one saving that is
  // actually visible — the motion stays correct thanks to the time scaling
  // below, but it reads as less fluid. The cost is taken out of the work per
  // frame instead (see the neighbour grid), which the eye cannot see at all.
  function setPowerSaving(_enabled: boolean) {
    frameBudgetMs = 1000 / 60;
  }

  // Idle freeze. Capping the rate still leaves a full-screen additive-blended
  // scene redrawing forever behind an idle app, which measurably heats the
  // machine. After a few quiet seconds the loop stops entirely and the last
  // frame simply stays on screen — visually near-identical to particles
  // drifting a fraction of a unit, at zero cost. Any sign of activity resumes
  // it immediately.
  const IDLE_FREEZE_MS = 6000;
  let lastActivity = performance.now();
  let frozen = false;

  function wake() {
    lastActivity = performance.now();
    if (!frozen || destroyed || paused) return;
    frozen = false;
    lastAnimationTick = performance.now();
    frameAccumulatorMs = frameBudgetMs;
    animate();
  }

  // Exponential decays must be raised to the power of k, not multiplied by it,
  // or the damping changes character with the frame rate.
  function decay(factor: number, k: number): number {
    return k === 1 ? factor : Math.pow(factor, k);
  }

  function animate() {
    if (destroyed || paused) return;

    const now = performance.now();
    requestAnimationFrame(animate);

    // Keep a real accumulator instead of resetting the clock after every
    // render. On 120/144 Hz displays the old reset drifted down to an uneven
    // 48 FPS. Fixed 60 Hz simulation steps preserve both speed and cadence.
    const elapsed = Math.min(Math.max(0, now - lastAnimationTick), 50);
    lastAnimationTick = now;
    frameAccumulatorMs += elapsed;
    if (frameAccumulatorMs < frameBudgetMs - 0.25) return;
    const steps = Math.max(1, Math.min(3, Math.floor(frameAccumulatorMs / frameBudgetMs)));
    frameAccumulatorMs = Math.max(0, frameAccumulatorMs - steps * frameBudgetMs);
    const k = steps * frameBudgetMs / FRAME_60HZ_MS;
    drawFrame(k, clock.getElapsedTime());
  }

  /** Advance and draw exactly one frame.
   *
   * Split out of the animation loop so a recorder can drive the scene on its
   * own clock. `requestAnimationFrame` is throttled to a standstill in a
   * background window, which would otherwise make capturing the real animation
   * impossible. `k` is the frame's length relative to 60 Hz. */
  function drawFrame(k: number, t: number) {
    frame++;

    switch (state) {
      case "idle":
        targetRadius = 28; targetSpeed = 0.2; targetBright = 0.5; targetSize = 0.35;
        targetLineAmount = 0.15; targetElectronRate = 0; break;
      case "listening":
        targetRadius = 22; targetSpeed = 0.3; targetBright = 0.65; targetSize = 0.4;
        targetLineAmount = 0.4; targetElectronRate = 0; break;
      case "thinking":
        targetRadius = 16; targetSpeed = 0.5; targetBright = 0.7; targetSize = 0.3;
        targetLineAmount = 1.0; targetElectronRate = 0.015; break;
      case "speaking":
        targetRadius = 18; targetSpeed = 0.2; targetBright = 0.7; targetSize = 0.4;
        targetLineAmount = 0.8; targetElectronRate = 0; break;
    }

    // A per-frame lerp of 0.02 becomes 1 - 0.98^k once k frames' worth of time
    // has passed, which is the same easing curve sampled less often.
    const ease = 1 - decay(0.98, k);
    currentRadius += (targetRadius - currentRadius) * ease;
    currentSpeed += (targetSpeed - currentSpeed) * ease;
    currentBright += (targetBright - currentBright) * ease;
    currentSize += (targetSize - currentSize) * ease;
    lineAmount += (targetLineAmount - lineAmount) * ease;
    electronSpawnRate += (targetElectronRate - electronSpawnRate) * ease;

    // Transition energy
    if (state !== lastState) { transitionEnergy = 1.0; lastState = state; }
    transitionEnergy *= decay(0.985, k);
    if (transitionEnergy > 0.05) {
      spinX += transitionEnergy * 0.012 * Math.sin(t * 1.7) * k;
      spinY += transitionEnergy * 0.015 * k;
      spinZ += transitionEnergy * 0.008 * Math.cos(t * 1.3) * k;
    }

    // Audio
    let rawBass = 0, rawMid = 0;
    if (analyser) {
      analyser.getByteFrequencyData(freqData);
      let bSum = 0, mSum = 0;
      for (let i = 0; i < 8; i++) bSum += freqData[i];
      for (let i = 8; i < 24; i++) mSum += freqData[i];
      rawBass = bSum / (8 * 255); rawMid = mSum / (16 * 255);
    }
    // A second, short attack/release stage turns analyser-bin jitter into a
    // fluid pulse while remaining visibly synchronized with each syllable.
    const audioEase = 1 - decay(analyser ? 0.72 : 0.88, k);
    bass += (rawBass - bass) * audioEase;
    mid += (rawMid - mid) * audioEase;

    // Depth Z breathing
    let zTarget = Math.sin(t * 0.12) * 8;
    if (state === "thinking") zTarget = Math.sin(t * 0.3) * 15 + Math.sin(t * 0.9) * 6;
    else if (state === "speaking") zTarget = Math.sin(t * 0.15) * 6 - bass * 10;
    cloudZVel += (zTarget - cloudZ) * 0.008 * k;
    cloudZVel *= decay(0.94, k);
    cloudZ += cloudZVel * k;

    points.rotation.x = spinX; points.rotation.y = spinY; points.rotation.z = spinZ;
    points.position.z = cloudZ;
    lines.rotation.x = spinX; lines.rotation.y = spinY; lines.rotation.z = spinZ;
    lines.position.z = cloudZ;

    // ── Update particles ──
    const p = geo.getAttribute("position") as THREE.BufferAttribute;
    const a = p.array as Float32Array;

    for (let i = 0; i < N; i++) {
      const i3 = i * 3;
      let x = a[i3], y = a[i3 + 1], z = a[i3 + 2];
      const px = phase[i];

      const drift = 0.001 * currentSpeed * k;
      const swirl = 0.0008 * currentSpeed * k;
      vel[i3] += Math.sin(t * 0.05 + px) * drift;
      vel[i3 + 1] += Math.cos(t * 0.06 + px * 1.3) * drift;
      vel[i3 + 2] += Math.sin(t * 0.055 + px * 0.7) * drift;
      vel[i3] += Math.sin(t * 0.02 + px * 2.1 + y * 0.1) * swirl;
      vel[i3 + 1] += Math.cos(t * 0.025 + px * 1.7 + z * 0.1) * swirl;
      vel[i3 + 2] += Math.sin(t * 0.022 + px * 0.9 + x * 0.1) * swirl;

      const dist = Math.sqrt(x * x + y * y + z * z) || 0.01;
      const pull = (Math.max(0, dist - currentRadius) * 0.002 + 0.0003) * k;
      vel[i3] -= (x / dist) * pull;
      vel[i3 + 1] -= (y / dist) * pull;
      vel[i3 + 2] -= (z / dist) * pull;

      if (bass > 0.05) {
        const kick = bass * 0.02 * k;
        vel[i3] += (x / dist) * kick;
        vel[i3 + 1] += (y / dist) * kick;
        vel[i3 + 2] += (z / dist) * kick;
      }
      if (state === "speaking" && mid > 0.1) {
        const pulse = Math.sin(t * 8 + px) * mid * 0.012 * k;
        vel[i3] += (x / dist) * pulse;
        vel[i3 + 1] += (y / dist) * pulse;
      }

      const damp = decay(0.992, k);
      vel[i3] *= damp; vel[i3 + 1] *= damp; vel[i3 + 2] *= damp;
      a[i3] += vel[i3] * k; a[i3 + 1] += vel[i3 + 1] * k; a[i3 + 2] += vel[i3 + 2] * k;
    }
    p.needsUpdate = true;

    // ── Update lines ──
    // Finding which particles are close enough to connect used to compare
    // every sampled pair — 222,111 distance checks per rebuild. Two particles
    // can only be within `maxDist` if they share a cell of that size or sit in
    // neighbouring ones, so binning them first and looking only at the 27
    // surrounding cells finds exactly the same pairs for a fraction of the
    // work. The drawn result is identical; only the order changes, and the
    // line budget is never reached at this particle count.
    if (lineAmount > 0.01) {
      lineMat.opacity = lineAmount * 0.12;
      if (frame % LINE_REBUILD_INTERVAL === 0) {
        const lp = lineGeo.getAttribute("position") as THREE.BufferAttribute;
        const la = lp.array as Float32Array;
        let lineCount = 0;
        const maxDist = lineDistance * (1 + bass * 0.5);
        const maxDistSq = maxDist * maxDist;
        const step = Math.max(1, Math.floor(N / 600));

        // Bin the sampled particles. Counting sort keeps this allocation-free:
        // one pass to count per cell, one to turn counts into offsets, one to
        // place each particle.
        sampleCount = 0;
        for (let i = 0; i < N; i += step) sampleIndex[sampleCount++] = i;

        cellCount.fill(0);
        for (let s = 0; s < sampleCount; s++) {
          const i3 = sampleIndex[s] * 3;
          const cell = cellOf(a[i3], a[i3 + 1], a[i3 + 2], maxDist);
          sampleCell[s] = cell;
          cellCount[cell]++;
        }
        let running = 0;
        for (let c = 0; c < CELL_TOTAL; c++) {
          cellStart[c] = running;
          running += cellCount[c];
          cellFill[c] = cellStart[c];
        }
        for (let s = 0; s < sampleCount; s++) cellItems[cellFill[sampleCell[s]]++] = sampleIndex[s];

        for (let s = 0; s < sampleCount && lineCount < MAX_LINES; s++) {
          const i = sampleIndex[s];
          const i3 = i * 3;
          const x1 = a[i3], y1 = a[i3 + 1], z1 = a[i3 + 2];
          const cx = axisOf(x1, maxDist), cy = axisOf(y1, maxDist), cz = axisOf(z1, maxDist);

          for (let ox = -1; ox <= 1 && lineCount < MAX_LINES; ox++) {
            const gx = cx + ox;
            if (gx < 0 || gx >= CELL_AXIS) continue;
            for (let oy = -1; oy <= 1 && lineCount < MAX_LINES; oy++) {
              const gy = cy + oy;
              if (gy < 0 || gy >= CELL_AXIS) continue;
              for (let oz = -1; oz <= 1 && lineCount < MAX_LINES; oz++) {
                const gz = cz + oz;
                if (gz < 0 || gz >= CELL_AXIS) continue;
                const cell = (gx * CELL_AXIS + gy) * CELL_AXIS + gz;
                const end = cellStart[cell] + cellCount[cell];
                for (let m = cellStart[cell]; m < end && lineCount < MAX_LINES; m++) {
                  const j = cellItems[m];
                  // Each pair once: the original loop only looked forward.
                  if (j <= i) continue;
                  const j3 = j * 3;
                  const dx = a[j3] - x1, dy = a[j3 + 1] - y1, dz = a[j3 + 2] - z1;
                  if (dx * dx + dy * dy + dz * dz < maxDistSq) {
                    const idx = lineCount * 6;
                    la[idx] = x1; la[idx+1] = y1; la[idx+2] = z1;
                    la[idx+3] = a[j3]; la[idx+4] = a[j3+1]; la[idx+5] = a[j3+2];
                    lineCount++;
                  }
                }
              }
            }
          }
        }
        lineGeo.setDrawRange(0, lineCount * 2);
        lp.needsUpdate = true;

        // Connections are only read to launch electrons, which fly during
        // "thinking" alone. Rebuilding this list the rest of the time would
        // allocate hundreds of objects per frame for nothing.
        activeConnections.length = 0;
        if (electronSpawnRate > 0.005) {
          for (let c = 0; c < Math.min(lineCount, 500); c++) {
            const ci = c * 6;
            activeConnections.push({
              x1: la[ci], y1: la[ci+1], z1: la[ci+2],
              x2: la[ci+3], y2: la[ci+4], z2: la[ci+5],
            });
          }
        }
      }
    } else {
      lineGeo.setDrawRange(0, 0);
      activeConnections.length = 0;
    }

    // ── Update electrons — only during thinking ──
    // One fires off every ~1 second, max 3 alive, takes 2-4s to travel
    if (activeConnections.length > 0 && electronSpawnRate > 0.005) {
      if (activeElectrons.length < 3 && (t - lastElectronSpawn) > 1.0) {
        const conn = activeConnections[Math.floor(Math.random() * activeConnections.length)];
        // speed: 1/fps * speed = progress per frame. At 60fps, speed 0.005 = 200 frames = 3.3s
        activeElectrons.push({
          sx: conn.x1, sy: conn.y1, sz: conn.z1,
          ex: conn.x2, ey: conn.y2, ez: conn.z2,
          t: 0,
          speed: 0.003 + Math.random() * 0.003, // 2-4 seconds to travel
        });
        lastElectronSpawn = t;
      }
    }

    // Update electron positions
    const ep = electronGeo.getAttribute("position") as THREE.BufferAttribute;
    const ea = ep.array as Float32Array;
    let aliveCount = 0;

    for (let e = activeElectrons.length - 1; e >= 0; e--) {
      const el = activeElectrons[e];
      el.t += el.speed * k;
      if (el.t >= 1) {
        activeElectrons.splice(e, 1);
        continue;
      }
      const ei = aliveCount * 3;
      ea[ei] = el.sx + (el.ex - el.sx) * el.t;
      ea[ei + 1] = el.sy + (el.ey - el.sy) * el.t;
      ea[ei + 2] = el.sz + (el.ez - el.sz) * el.t;
      aliveCount++;
    }

    electronGeo.setDrawRange(0, aliveCount);
    ep.needsUpdate = true;

    // Electrons follow the same rotation/position as the main group
    electrons.rotation.x = spinX; electrons.rotation.y = spinY; electrons.rotation.z = spinZ;
    electrons.position.z = cloudZ;

    mat.opacity = currentBright + bass * 0.08;
    mat.size = currentSize + bass * 0.05;

    const tint = state === "thinking" ? THINKING_COLOR : state === "speaking" ? SPEAKING_COLOR : IDLE_COLOR;
    const tintEase = 1 - decay(0.985, k);
    mat.color.lerp(tint, tintEase);
    lineMat.color.lerp(tint, tintEase);

    camera.position.x = Math.sin(t * 0.02) * 5;
    camera.position.y = Math.cos(t * 0.03) * 3;
    camera.lookAt(0, 0, cloudZ * 0.2);

    renderer.render(scene, camera);
  }

  function onResize() {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
  }

  // A hidden window still burned a full animation loop. Stopping outright
  // costs nothing while JARVIS sits behind another app, which is most of the
  // time it is running.
  function onVisibilityChange() {
    const hidden = document.hidden;
    if (hidden === paused) return;
    paused = hidden;
    if (paused) return;
    // Becoming visible counts as activity, otherwise a window revealed while
    // the loop was frozen would stay frozen.
    lastActivity = performance.now();
    lastAnimationTick = lastActivity;
    frameAccumulatorMs = frameBudgetMs;
    frozen = false;
    animate();
  }

  const WAKE_EVENTS = ["pointermove", "pointerdown", "keydown", "wheel"] as const;

  window.addEventListener("resize", onResize);
  document.addEventListener("visibilitychange", onVisibilityChange);
  for (const name of WAKE_EVENTS) window.addEventListener(name, wake, { passive: true });
  window.addEventListener("focus", wake);
  animate();

  return {
    setState(s: OrbState) {
      if (s !== state) wake();
      state = s;
      // Keep one cadence in every state. Changing cadence during the morph was
      // itself visible as a hitch on high-refresh Windows displays.
      setPowerSaving(s === "idle" || s === "listening");
    },
    setPowerSaving,
    step: drawFrame,
    detachLoop() {
      // Park the self-driven loop; the caller now decides when frames happen.
      paused = true;
    },
    setAnalyser(a: AnalyserNode | null) {
      analyser = a;
      if (a) freqData = new Uint8Array(a.frequencyBinCount);
    },
    destroy() {
      destroyed = true;
      window.removeEventListener("resize", onResize);
      document.removeEventListener("visibilitychange", onVisibilityChange);
      for (const name of WAKE_EVENTS) window.removeEventListener(name, wake);
      window.removeEventListener("focus", wake);
      renderer.dispose();
    },
  };
}
