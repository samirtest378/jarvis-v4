/** Local-first voice input and audio output for JARVIS. */

import { apiUrl, authHeaders, getDesktopBridge } from "./runtime";
import { inferSpeechLanguage, selectBrowserSpeechVoice } from "./speech_preferences.js";
import { floatToPcmWav } from "./speech_audio.js";
import {
  audioPlaybackWatchdogMs,
  browserSpeechWatchdogMs,
  classifySpeechFrame,
  shouldSubmitSpeechWindow,
} from "./voice_activity.js";

// ---------------------------------------------------------------------------
// Speech Recognition
// ---------------------------------------------------------------------------

export interface VoiceInput {
  start(): void;
  stop(): void;
  /** `keepOpen` holds the microphone through a reply; see the recorder. */
  pause(keepOpen?: boolean): void;
  resume(): void;
  setLanguage(language: string): void;
  isSupported(): boolean;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
declare const webkitSpeechRecognition: any;

function createSystemSpeechInput(
  onTranscript: (text: string) => boolean | void,
  onError: (msg: string) => void
): VoiceInput {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const SR = (window as any).SpeechRecognition || (typeof webkitSpeechRecognition !== "undefined" ? webkitSpeechRecognition : null);
  if (!SR) {
      onError("Speech recognition is unavailable on this computer.");
    return { start() {}, stop() {}, pause() {}, resume() {}, setLanguage() {}, isSupported() { return false; } };
  }

  const recognition = new SR();
  recognition.continuous = true;
  recognition.interimResults = true;
  let languageMode = "auto";
  const systemLanguage = String(navigator.language || "de-DE");
  recognition.lang = /^(?:de|en)(?:-|$)/i.test(systemLanguage) ? systemLanguage : "de-DE";

  let shouldListen = false;
  let paused = false;

  recognition.onresult = (event: any) => {
    for (let i = event.resultIndex; i < event.results.length; i++) {
      if (event.results[i].isFinal) {
        const text = event.results[i][0].transcript.trim();
        if (text) {
          if (languageMode === "auto") {
            // Browser recognition cannot request true bilingual auto-detection.
            // Learn from every accepted sentence so the next fallback turn
            // follows an English/German switch instead of staying hard-coded.
            recognition.lang = inferSpeechLanguage(text, "auto");
          }
          onTranscript(text);
        }
      }
    }
  };

  recognition.onend = () => {
    if (shouldListen && !paused) {
      try {
        recognition.start();
      } catch {
        // Already started
      }
    }
  };

  recognition.onerror = (event: any) => {
    if (event.error === "not-allowed") {
      onError("Microphone access denied. Please allow microphone access.");
      shouldListen = false;
    } else if (event.error === "no-speech") {
      // Normal, just restart
    } else if (event.error === "aborted") {
      // Expected during pause
    } else if (event.error === "network") {
      onError("The operating-system speech service is unavailable. Local Whisper is recommended.");
      shouldListen = false;
    } else {
      console.warn("[voice] recognition error:", event.error);
    }
  };

  return {
    start() {
      shouldListen = true;
      paused = false;
      try {
        recognition.start();
      } catch {
        // Already started
      }
    },
    stop() {
      shouldListen = false;
      paused = false;
      recognition.stop();
    },
    pause() {
      paused = true;
      recognition.stop();
    },
    resume() {
      paused = false;
      if (shouldListen) {
        try {
          recognition.start();
        } catch {
          // Already started
        }
      }
    },
    setLanguage(language: string) {
      const normalized = language.trim();
      languageMode = normalized === "auto" ? "auto" : normalized;
      if (/^(?:de-DE|en-US|en-GB)$/.test(normalized)) {
        recognition.lang = normalized;
      } else if (normalized === "auto") {
        recognition.lang = /^(?:de|en)(?:-|$)/i.test(systemLanguage) ? systemLanguage : "de-DE";
      }
    },
    isSupported() {
      return true;
    },
  };
}

function createRecordedSpeechInput(
  onTranscript: (text: string) => boolean | void,
  onError: (msg: string) => void,
): VoiceInput {
  let language = "auto";
  let shouldListen = false;
  let paused = false;
  let starting: Promise<void> | null = null;
  let stream: MediaStream | null = null;
  let audioContext: AudioContext | null = null;
  let source: MediaStreamAudioSourceNode | null = null;
  let processor: ScriptProcessorNode | AudioWorkletNode | null = null;
  let silentGain: GainNode | null = null;
  let samples: number[] = [];
  let noiseFloor = 0.004;
  let calibrationFrames = 0;
  let voicedFrames = 0;
  let voicedSamples = 0;
  let trailingSilenceFrames = 0;
  let trailingSilenceSamples = 0;
  let speechStarted = false;
  let rmsTotal = 0;
  let rmsFrames = 0;
  let inferencePending = false;
  let stoppedGeneration = 0;

  const setLocalSpeechSession = (enabled: boolean) => {
    // Windows may throttle a hidden renderer. Keep the audio capture clock at
    // full speed only while the microphone is active, then return to normal
    // background power saving immediately when listening stops.
    void getDesktopBridge()?.setVoiceActivity(enabled);
    void fetch(apiUrl("/api/speech/session"), {
      method: "POST",
      headers: { ...authHeaders(), "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    }).catch(() => {
      // Transcription itself reports actionable errors. Prewarming is an
      // optimization, so a backend restart here must not disable the mic.
    });
  };

  const release = () => {
    setLocalSpeechSession(false);
    stoppedGeneration += 1;
    processor?.disconnect();
    source?.disconnect();
    silentGain?.disconnect();
    stream?.getTracks().forEach((track) => track.stop());
    if (audioContext && audioContext.state !== "closed") void audioContext.close();
    stream = null;
    audioContext = null;
    source = null;
    processor = null;
    silentGain = null;
    samples = [];
    noiseFloor = 0.004;
    calibrationFrames = 0;
    voicedFrames = 0;
    voicedSamples = 0;
    trailingSilenceFrames = 0;
    trailingSilenceSamples = 0;
    speechStarted = false;
    rmsTotal = 0;
    rmsFrames = 0;
    inferencePending = false;
    starting = null;
  };

  const submitWindow = async (generation: number) => {
    if (!audioContext || inferencePending || samples.length < audioContext.sampleRate * 0.55) return;
    // Require at least ~170 ms of energy clearly above the calibrated room
    // noise. This accepts short "ja"/"yes" replies while still rejecting a
    // single click, keyboard bump, or isolated peak.
    if (voicedFrames < 2) {
      if (rmsFrames > 0) noiseFloor = Math.max(noiseFloor, (rmsTotal / rmsFrames) * 1.05);
      samples = samples.slice(-Math.floor(audioContext.sampleRate * 0.35));
      voicedFrames = 0;
      voicedSamples = 0;
      trailingSilenceFrames = 0;
      trailingSilenceSamples = 0;
      speechStarted = false;
      rmsTotal = 0;
      rmsFrames = 0;
      return;
    }
    inferencePending = true;
    const rate = audioContext.sampleRate;
    const window = new Float32Array(samples.slice(-Math.floor(rate * 15)));
    const averageRms = rmsFrames > 0 ? rmsTotal / rmsFrames : 0;
    // Start the next utterance cleanly. Audio that arrives while inference is
    // running is appended by the processor and remains available afterwards.
    samples = [];
    voicedFrames = 0;
    voicedSamples = 0;
    trailingSilenceFrames = 0;
    trailingSilenceSamples = 0;
    speechStarted = false;
    rmsTotal = 0;
    rmsFrames = 0;
    try {
      const response = await fetch(apiUrl(`/api/speech/transcribe?language=${encodeURIComponent(language)}`), {
        method: "POST",
        headers: { ...authHeaders(), "Content-Type": "audio/wav" },
        body: floatToPcmWav(window, rate),
      });
      const payload = await response.json() as { success?: boolean; text?: string; error?: string };
      if (!response.ok || payload.success !== true) throw new Error(payload.error || "Speech recognition failed");
      const text = String(payload.text || "").trim();
      // Continuous background noise can sit above the initial calibration.
      // An empty local transcript is safe evidence that this window was not a
      // command, so fold its level into the floor before the next decision.
      if (!text && averageRms > 0) noiseFloor = Math.max(noiseFloor, averageRms * 1.05);
      if (text && generation === stoppedGeneration && shouldListen && !paused) {
        const accepted = onTranscript(text);
        if (accepted === false && averageRms > 0) {
          noiseFloor = Math.max(noiseFloor, averageRms * 1.05);
        }
      }
    } catch (error) {
      if (generation === stoppedGeneration && shouldListen) {
        onError(error instanceof Error ? error.message : "Speech recognition failed");
      }
    } finally {
      inferencePending = false;
      if (generation === stoppedGeneration && shouldListen && !paused) void submitWindow(generation);
    }
  };

  const open = async () => {
    if (stream || starting) return starting || Promise.resolve();
    const generation = stoppedGeneration;
    starting = (async () => {
      if (!navigator.mediaDevices?.getUserMedia) throw new Error("Microphone recording is unavailable on this computer.");
      stream = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true, autoGainControl: true },
        video: false,
      });
      if (generation !== stoppedGeneration || !shouldListen) {
        stream.getTracks().forEach((track) => track.stop());
        stream = null;
        return;
      }
      audioContext = new AudioContext({ latencyHint: "interactive" });
      // Start loading the bundled model while the user begins speaking. Once
      // loaded it remains resident only for this listening session, removing
      // the cold-start delay from "Hey JARVIS" without background CPU work.
      setLocalSpeechSession(true);
      source = audioContext.createMediaStreamSource(stream);
      silentGain = audioContext.createGain();
      silentGain.gain.value = 0;

      const captureSamples = (channel: Float32Array) => {
        if (!shouldListen || paused) return;
        let energy = 0;
        for (let index = 0; index < channel.length; index++) {
          const value = channel[index];
          samples.push(value);
          energy += value * value;
        }
        const rms = Math.sqrt(energy / channel.length);
        rmsTotal += rms;
        rmsFrames += 1;
        const classified = classifySpeechFrame({
          rms,
          noiseFloor,
          calibrationFrames,
          speechStarted,
        });
        noiseFloor = classified.noiseFloor;
        calibrationFrames = classified.calibrationFrames;
        if (classified.voiced) {
          voicedFrames += 1;
          voicedSamples += channel.length;
          trailingSilenceFrames = 0;
          trailingSilenceSamples = 0;
          speechStarted = true;
        } else if (speechStarted) {
          trailingSilenceFrames += 1;
          trailingSilenceSamples += channel.length;
        }
        if (audioContext && !speechStarted && samples.length > audioContext.sampleRate * 0.45) {
          // Retain enough lead-in to preserve the first consonant, but do not
          // send seconds of silence to Whisper. Smaller windows transcribe
          // faster and reduce hallucinations in always-on mode.
          samples = samples.slice(-Math.floor(audioContext.sampleRate * 0.45));
          rmsTotal = rms;
          rmsFrames = 1;
        }
        if (audioContext && (
          shouldSubmitSpeechWindow({
            sampleCount: samples.length,
            sampleRate: audioContext.sampleRate,
            voicedFrames,
            voicedSamples,
            trailingSilenceFrames,
            trailingSilenceSamples,
          })
          || samples.length >= audioContext.sampleRate * 15
        )) void submitWindow(generation);
      };

      // AudioWorklet runs capture outside the renderer's UI thread. This is
      // especially important on Windows where WebGL animation, antivirus and
      // window compositing can otherwise make ScriptProcessor drop frames.
      // Keep a fallback for older browsers used during development.
      if (audioContext.audioWorklet && typeof AudioWorkletNode !== "undefined") {
        try {
          await audioContext.audioWorklet.addModule("/audio-capture-worklet.js");
          const worklet = new AudioWorkletNode(audioContext, "jarvis-audio-capture", {
            numberOfInputs: 1,
            numberOfOutputs: 1,
            outputChannelCount: [1],
            channelCount: 1,
          });
          worklet.port.onmessage = (event: MessageEvent<Float32Array>) => {
            if (event.data instanceof Float32Array) captureSamples(event.data);
          };
          processor = worklet;
        } catch (error) {
          console.warn("[voice] AudioWorklet unavailable, using compatible capture:", error);
        }
      }
      if (!processor) {
        const fallback = audioContext.createScriptProcessor(2048, 1, 1);
        fallback.onaudioprocess = (event) => captureSamples(event.inputBuffer.getChannelData(0));
        processor = fallback;
      }
      source.connect(processor);
      processor.connect(silentGain);
      silentGain.connect(audioContext.destination);
      if (audioContext.state === "suspended") await audioContext.resume();
    })().catch((error) => {
      release();
      const message = error instanceof DOMException && error.name === "NotAllowedError"
        ? "Microphone access denied. Please allow microphone access."
        : error instanceof Error ? error.message : "Microphone recording failed.";
      onError(message);
    }).finally(() => { starting = null; });
    return starting;
  };

  return {
    start() {
      shouldListen = true;
      paused = false;
      void open();
    },
    stop() {
      shouldListen = false;
      paused = false;
      release();
    },
    pause(keepOpen = false) {
      paused = true;
      samples = [];
      voicedFrames = 0;
      voicedSamples = 0;
      trailingSilenceFrames = 0;
      trailingSilenceSamples = 0;
      speechStarted = false;
      rmsTotal = 0;
      rmsFrames = 0;
      // Normally the microphone is handed back to the system, so the device is
      // not powered and the recording indicator is not lit while JARVIS thinks
      // and speaks.
      //
      // `keepOpen` is for a conversation in wake-phrase mode: reopening costs
      // a moment, and a reply that lands while the device is still coming back
      // up loses its first word. The microphone is staying on for the session
      // anyway in that mode, so holding it through the reply costs nothing
      // extra and keeps the exchange responsive.
      if (!keepOpen) release();
    },
    resume() {
      paused = false;
      samples = [];
      voicedFrames = 0;
      voicedSamples = 0;
      trailingSilenceFrames = 0;
      trailingSilenceSamples = 0;
      speechStarted = false;
      rmsTotal = 0;
      rmsFrames = 0;
      if (shouldListen) void open();
    },
    setLanguage(value: string) {
      if (/^(?:auto|de-DE|en-US|en-GB)$/.test(value.trim())) language = value.trim();
    },
    isSupported() {
      return Boolean(navigator.mediaDevices?.getUserMedia);
    },
  };
}

/** Prefer recorded audio with the configured backend and use OS speech only as a fallback. */
export function createVoiceInput(
  onTranscript: (text: string) => boolean | void,
  onError: (msg: string) => void,
): VoiceInput {
  const recorded = createRecordedSpeechInput(onTranscript, onError);
  const system = createSystemSpeechInput(onTranscript, onError);
  let selected: VoiceInput | null = null;
  let language = "auto";
  let shouldListen = false;
  let paused = false;
  let selecting: Promise<void> | null = null;

  const select = async () => {
    if (selected || selecting) return selecting || Promise.resolve();
    selecting = (async () => {
      try {
        const response = await fetch(apiUrl("/api/speech/status"), { headers: authHeaders() });
        const status = await response.json() as {
          active_provider?: "openai" | "fish" | "local" | "off";
          local_ready?: boolean;
        };
        const canRecord = response.ok
          && status.active_provider !== "off"
          && (status.active_provider !== "local" || status.local_ready === true);
        selected = canRecord ? recorded : system;
      } catch {
        selected = system;
      }
      selected.setLanguage(language);
      if (shouldListen) {
        selected.start();
        if (paused) selected.pause();
      }
    })().finally(() => { selecting = null; });
    return selecting;
  };

  return {
    start() {
      shouldListen = true;
      paused = false;
      if (selected) selected.start(); else void select();
    },
    stop() {
      shouldListen = false;
      paused = false;
      selected?.stop();
    },
    pause(keepOpen = false) {
      paused = true;
      selected?.pause(keepOpen);
    },
    resume() {
      paused = false;
      if (shouldListen) selected ? selected.resume() : void select();
    },
    setLanguage(value: string) {
      language = value;
      recorded.setLanguage(value);
      system.setLanguage(value);
    },
    isSupported() {
      return recorded.isSupported() || system.isSupported();
    },
  };
}

// ---------------------------------------------------------------------------
// Audio Player
// ---------------------------------------------------------------------------

export interface AudioPlayer {
  enqueue(base64: string): Promise<void>;
  stop(): void;
  /** Null until the first sound is played — the audio graph is built lazily. */
  getAnalyser(): AnalyserNode | null;
  /** Called as soon as the analyser exists, so visuals can attach to it. */
  onAnalyser(cb: (analyser: AnalyserNode) => void): void;
  /** Satisfy the autoplay policy from a user gesture. Safe to call repeatedly. */
  unlock(): void;
  onFinished(cb: () => void): void;
}

export interface BrowserSpeechPlayer {
  speak(text: string): Promise<void>;
  stop(): void;
  isSupported(): boolean;
  setLanguage(value: string): void;
  /** Match short confirmations to the voice JARVIS otherwise speaks in. */
  setPreferredVoice(name: string): void;
  /** Language tag of the voice that will actually speak, once resolved. */
  voiceLanguage(): string;
}

/**
 * Last-resort speech output provided by Chromium and the operating system.
 *
 * The backend normally returns generated WAV/MP3 audio.  Some macOS voice
 * installations advertise a voice to the `say` command but return an empty
 * audio file. Windows and Linux likewise benefit from an immediate native
 * fallback. Keeping this independent path means the assistant remains audible
 * without sending text to another service.
 */
export function createBrowserSpeechPlayer(): BrowserSpeechPlayer {
  const supported = "speechSynthesis" in window && "SpeechSynthesisUtterance" in window;
  let generation = 0;
  let language = "en-GB";
  // The voice configured for JARVIS, so a short confirmation does not arrive in
  // a completely different voice from every other reply.
  let preferredVoiceName = "";

  // The voice list is populated asynchronously: the first `getVoices()` call
  // usually returns an empty array, and an empty list means no voice is chosen
  // and the platform default speaks instead — on a German Mac that is Anna,
  // which is exactly the "somebody else answered" problem. Cache the list and
  // refresh it when the browser says it has changed.
  let cachedVoices: SpeechSynthesisVoice[] = [];
  const refreshVoices = () => {
    if (!supported) return;
    const voices = window.speechSynthesis.getVoices();
    if (voices.length) cachedVoices = voices;
  };
  if (supported) {
    refreshVoices();
    window.speechSynthesis.addEventListener?.("voiceschanged", refreshVoices);
  }

  const resolveVoice = (requestedLanguage = language) => {
    refreshVoices();
    return selectBrowserSpeechVoice(cachedVoices, requestedLanguage, preferredVoiceName);
  };

  return {
    speak(text: string) {
      const normalized = text.trim();
      if (!supported || !normalized) {
        return Promise.reject(new Error("The built-in system voice is unavailable"));
      }
      generation += 1;
      const requestGeneration = generation;
      window.speechSynthesis.cancel();

      return new Promise<void>((resolve, reject) => {
        const utteranceLanguage = inferSpeechLanguage(normalized, language);
        const utterance = new SpeechSynthesisUtterance(normalized);
        utterance.voice = resolveVoice(utteranceLanguage);
        utterance.lang = utterance.voice?.lang || utteranceLanguage;
        utterance.rate = 0.95;
        let settled = false;
        let watchdog = 0;
        const finish = (error?: Error) => {
          if (settled) return;
          settled = true;
          window.clearTimeout(watchdog);
          if (error) reject(error);
          else resolve();
        };
        utterance.onend = () => finish();
        utterance.onerror = (event) => {
          if (requestGeneration !== generation || event.error === "canceled" || event.error === "interrupted") {
            finish();
          } else {
            finish(new Error(`System voice failed: ${event.error}`));
          }
        };
        window.speechSynthesis.speak(utterance);
        watchdog = window.setTimeout(() => {
          if (requestGeneration === generation) window.speechSynthesis.cancel();
          finish();
        }, browserSpeechWatchdogMs(normalized));
      });
    },

    stop() {
      generation += 1;
      if (supported) window.speechSynthesis.cancel();
    },

    isSupported() {
      return supported;
    },

    setLanguage(value: string) {
      const normalized = value.trim();
      if (normalized) language = normalized;
    },

    setPreferredVoice(name: string) {
      preferredVoiceName = String(name || "").trim();
    },

    voiceLanguage() {
      const resolvedLanguage = inferSpeechLanguage("", language);
      return resolveVoice(resolvedLanguage)?.lang || resolvedLanguage;
    },
  };
}

export function createAudioPlayer(): AudioPlayer {
  // Built on first use, not at startup. A running AudioContext keeps the
  // browser's audio service awake for the whole session — measured at ~7% of a
  // CPU core on an idle machine that was playing nothing at all.
  let audioCtx: AudioContext | null = null;
  let analyser: AnalyserNode | null = null;
  let analyserCallback: ((analyser: AnalyserNode) => void) | null = null;
  let suspendTimer = 0;
  let unlocked = false;

  function ensureContext(): { context: AudioContext; node: AnalyserNode } {
    if (!audioCtx || !analyser) {
      audioCtx = new AudioContext();
      analyser = audioCtx.createAnalyser();
      analyser.fftSize = 256;
      analyser.smoothingTimeConstant = 0.8;
      analyser.connect(audioCtx.destination);
      analyserCallback?.(analyser);
    }
    return { context: audioCtx, node: analyser };
  }

  const queue: AudioBuffer[] = [];
  let isPlaying = false;
  let currentSource: AudioBufferSourceNode | null = null;
  let sourceWatchdog = 0;
  let finishedCallback: (() => void) | null = null;

  // Suspending returns the audio service to idle. The short delay avoids
  // churning the device between two sentences of the same reply.
  function scheduleSuspend() {
    window.clearTimeout(suspendTimer);
    suspendTimer = window.setTimeout(() => {
      if (!isPlaying && audioCtx?.state === "running") void audioCtx.suspend();
    }, 1500);
  }

  function playNext() {
    if (queue.length === 0) {
      isPlaying = false;
      currentSource = null;
      finishedCallback?.();
      scheduleSuspend();
      return;
    }

    isPlaying = true;
    const { context, node } = ensureContext();
    const buffer = queue.shift()!;
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(node);
    currentSource = source;

    const finishSource = () => {
      if (currentSource !== source) return;
      window.clearTimeout(sourceWatchdog);
      sourceWatchdog = 0;
      currentSource = null;
      playNext();
    };
    source.onended = finishSource;

    source.start();
    // Chromium occasionally loses `onended` when macOS switches the audio
    // route while the microphone is held open for wake mode. Never leave the
    // UI stuck on “Speaking…”: the decoded buffer duration is authoritative.
    sourceWatchdog = window.setTimeout(finishSource, audioPlaybackWatchdogMs(buffer.duration));
  }

  return {
    async enqueue(base64: string) {
      const { context } = ensureContext();
      window.clearTimeout(suspendTimer);
      // Resume audio context (browser autoplay policy, and our own suspend)
      if (context.state !== "running" && context.state !== "closed") {
        await context.resume();
      }

      try {
        const binary = atob(base64);
        const bytes = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i++) {
          bytes[i] = binary.charCodeAt(i);
        }
        const audioBuffer = await context.decodeAudioData(bytes.buffer.slice(0));
        queue.push(audioBuffer);
        if (!isPlaying) playNext();
      } catch (err) {
        console.error("[audio] decode error:", err);
        // Skip bad audio, continue, and let the caller activate its local
        // system-speech fallback rather than silently pretending it played.
        if (!isPlaying && queue.length > 0) playNext();
        throw err;
      }
    },

    stop() {
      queue.length = 0;
      window.clearTimeout(sourceWatchdog);
      sourceWatchdog = 0;
      if (currentSource) {
        try {
          currentSource.stop();
        } catch {
          // Already stopped
        }
        currentSource = null;
      }
      isPlaying = false;
      scheduleSuspend();
    },

    getAnalyser() {
      return analyser;
    },

    onAnalyser(cb: (node: AnalyserNode) => void) {
      analyserCallback = cb;
      if (analyser) cb(analyser);
    },

    unlock() {
      // A single user gesture satisfies the autoplay policy for the rest of the
      // session, so this runs once and then hands the device straight back.
      if (unlocked) return;
      unlocked = true;
      const { context } = ensureContext();
      if (context.state === "suspended") void context.resume().then(scheduleSuspend);
      else scheduleSuspend();
    },

    onFinished(cb: () => void) {
      finishedCallback = cb;
    },
  };
}
