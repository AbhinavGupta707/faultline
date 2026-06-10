// Framework-agnostic Web Audio helpers for the voice feature.
//  Recorder: mic → 16 kHz mono PCM16 frames (via an AudioWorklet loaded from a Blob URL,
//            so no bundler/worklet-file config is needed).
//  Player:   queued 24 kHz PCM16 playback with an AnalyserNode for the waveform.

/* eslint-disable @typescript-eslint/no-explicit-any */

const WORKLET_SRC = `
class PCMRecorder extends AudioWorkletProcessor {
  constructor(opts){ super(); this.target = opts.processorOptions.targetRate; this.pos = 0; }
  process(inputs){
    const ch = inputs[0][0];
    if(!ch) return true;
    const ratio = sampleRate / this.target;
    const out = [];
    for(let i = this.pos; i < ch.length; i += ratio){
      const idx = Math.floor(i), a = ch[idx] || 0, b = (ch[idx+1] !== undefined ? ch[idx+1] : a);
      out.push(a + (b - a) * (i - idx));
    }
    this.pos = (Math.ceil((ch.length - this.pos) / ratio) * ratio) - (ch.length - this.pos);
    if(this.pos < 0) this.pos = 0;
    const i16 = new Int16Array(out.length);
    for(let i = 0; i < out.length; i++){ let s = Math.max(-1, Math.min(1, out[i])); i16[i] = s < 0 ? s*32768 : s*32767; }
    if(i16.length) this.port.postMessage(i16.buffer, [i16.buffer]);
    return true;
  }
}
registerProcessor('pcm-recorder', PCMRecorder);
`;

let workletURL: string | null = null;
function getWorkletURL(): string {
  if (!workletURL) {
    workletURL = URL.createObjectURL(new Blob([WORKLET_SRC], { type: "application/javascript" }));
  }
  return workletURL;
}

const AC: typeof AudioContext = (window as any).AudioContext || (window as any).webkitAudioContext;

export class Recorder {
  private ctx: AudioContext | null = null;
  private stream: MediaStream | null = null;
  private node: AudioWorkletNode | null = null;

  async start(onFrame: (pcm: ArrayBuffer) => void): Promise<void> {
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
    });
    this.ctx = new AC();
    await this.ctx.audioWorklet.addModule(getWorkletURL());
    const src = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, "pcm-recorder", {
      processorOptions: { targetRate: 16000 },
    });
    this.node.port.onmessage = (e: MessageEvent) => onFrame(e.data as ArrayBuffer);
    src.connect(this.node);
  }

  stop(): void {
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.ctx?.close();
    this.node = this.stream = this.ctx = null;
  }
}

export class Player {
  private ctx: AudioContext | null = null;
  private rate = 24000;
  private nextTime = 0;
  analyser: AnalyserNode | null = null;

  ensure(rate: number): void {
    if (!this.ctx || this.ctx.sampleRate !== rate) {
      this.ctx?.close();
      this.ctx = new AC({ sampleRate: rate });
      this.rate = rate;
      this.analyser = this.ctx.createAnalyser();
      this.analyser.fftSize = 1024;
      this.analyser.connect(this.ctx.destination);
      this.nextTime = this.ctx.currentTime;
    }
    if (this.ctx.state === "suspended") void this.ctx.resume();
  }

  push(pcm16: ArrayBuffer): void {
    if (!this.ctx || !this.analyser) this.ensure(this.rate);
    const ctx = this.ctx!;
    const i16 = new Int16Array(pcm16);
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const buf = ctx.createBuffer(1, f32.length, this.rate);
    buf.getChannelData(0).set(f32);
    const node = ctx.createBufferSource();
    node.buffer = buf;
    node.connect(this.analyser!);
    const t = Math.max(ctx.currentTime, this.nextTime);
    node.start(t);
    this.nextTime = t + buf.duration;
  }

  get speaking(): boolean {
    return !!this.ctx && this.nextTime > this.ctx.currentTime + 0.02;
  }

  close(): void {
    this.ctx?.close();
    this.ctx = this.analyser = null;
    this.nextTime = 0;
  }
}
