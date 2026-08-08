class JarvisAudioCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    // 2048 samples gives endpoint detection twice the temporal resolution of
    // the compatibility processor without increasing inference frequency.
    this.chunkSize = 2048;
    this.chunk = new Float32Array(this.chunkSize);
    this.offset = 0;
  }

  process(inputs, outputs) {
    const input = inputs[0]?.[0];
    if (input) {
      let sourceOffset = 0;
      while (sourceOffset < input.length) {
        const available = this.chunkSize - this.offset;
        const count = Math.min(available, input.length - sourceOffset);
        this.chunk.set(input.subarray(sourceOffset, sourceOffset + count), this.offset);
        this.offset += count;
        sourceOffset += count;
        if (this.offset === this.chunkSize) {
          const ready = this.chunk;
          this.port.postMessage(ready, [ready.buffer]);
          this.chunk = new Float32Array(this.chunkSize);
          this.offset = 0;
        }
      }
    }

    // The node remains connected through a zero-gain output so Chromium keeps
    // delivering microphone frames. Never copy microphone audio to speakers.
    for (const output of outputs) {
      for (const channel of output) channel.fill(0);
    }
    return true;
  }
}

registerProcessor("jarvis-audio-capture", JarvisAudioCaptureProcessor);
