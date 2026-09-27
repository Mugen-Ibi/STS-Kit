class PCMRecorder extends AudioWorkletProcessor {
  constructor() {
    super();
    this.pending = new Float32Array(1024);
    this.used = 0;
    this.port.onmessage = (event) => {
      if (event.data === 'flush') {
        this.flush();
        this.port.postMessage('flushed');
      }
    };
  }
  flush() {
    if (!this.used) return;
    const data = this.used === this.pending.length ? this.pending : this.pending.slice(0, this.used);
    this.port.postMessage(data.buffer, [data.buffer]);
    this.pending = new Float32Array(1024);
    this.used = 0;
  }
  process(inputs, outputs) {
    const channel = inputs[0]?.[0];
    if (channel) {
      for (let offset = 0; offset < channel.length;) {
        const count = Math.min(channel.length - offset, this.pending.length - this.used);
        this.pending.set(channel.subarray(offset, offset + count), this.used);
        this.used += count;
        offset += count;
        if (this.used === this.pending.length) this.flush();
      }
    }
    for (const output of outputs) for (const channel of output) channel.fill(0);
    return true;
  }
}
registerProcessor("pcm-recorder", PCMRecorder);
