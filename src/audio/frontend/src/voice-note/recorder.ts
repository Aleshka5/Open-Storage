// Microphone capture via AudioWorklet → 16 kHz mono → 100 ms PCM s16le frames.
// (chat-and-player.md §«Voice note»): getUserMedia with echoCancellation,
// noiseSuppression, autoGainControl; the AudioWorklet slices the stream into 100 ms
// chunks and resamples to 16 kHz, emitting one frame (3200 bytes) at a time to the socket.

import type { VoiceNoteRecorder } from './flow';
import { FRAME_BYTES } from './flow';

// AudioWorklet processor code. Resamples the incoming AudioBuffer into an output
// frame of 1600 samples (100 ms @ 16 kHz), s16le.
const WORKLET_SOURCE = `
class Pcm16kProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this._pending = new Float32Array(0);
  }
  process(inputs) {
    const input = inputs[0];
    const channel = input && input[0] ? input[0] : null;
    if (!channel) return true;
    const inRate = sampleRate;
    const target = 16000;
    let samples = channel;
    if (inRate !== target) {
      // Simple resampling by linear interpolation (good enough for 16 kHz ASR).
      const ratio = inRate / target;
      const outLen = Math.round(samples.length / ratio);
      const out = new Float32Array(outLen);
      for (let i = 0; i < outLen; i++) {
        const src = i * ratio;
        const i0 = Math.floor(src);
        const i1 = Math.min(i0 + 1, samples.length - 1);
        const t = src - i0;
        out[i] = samples[i0] * (1 - t) + samples[i1] * t;
      }
      samples = out;
    }
    this._pending = this._pending.length
      ? mergeFloat(this._pending, samples)
      : new Float32Array(samples);
    while (this._pending.length >= 1600) {
      const chunk = this._pending.subarray(0, 1600);
      const pcm = floatToS16(chunk);
      this.port.postMessage(pcm.buffer, [pcm.buffer]);
      this._pending = this._pending.subarray(1600);
    }
    return true;
  }
}
function mergeFloat(a, b) {
  const out = new Float32Array(a.length + b.length);
  out.set(a, 0);
  out.set(b, a.length);
  return out;
}
function floatToS16(f32) {
  const out = new Int16Array(f32.length);
  for (let i = 0; i < f32.length; i++) {
    const s = Math.max(-1, Math.min(1, f32[i]));
    out[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return out;
}
registerProcessor('pcm16k-processor', Pcm16kProcessor);
`;

export class WorkletRecorder implements VoiceNoteRecorder {
  private ctx: AudioContext | null = null;
  private node: AudioWorkletNode | null = null;
  private stream: MediaStream | null = null;
  private onFrame: ((pcm: ArrayBuffer) => void) | null = null;

  async start(onFrame: (pcm: ArrayBuffer) => void): Promise<void> {
    this.onFrame = onFrame;
    this.stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.ctx = new AudioContext();
    const blob = new Blob([WORKLET_SOURCE], { type: 'application/javascript' });
    const url = URL.createObjectURL(blob);
    await this.ctx.audioWorklet.addModule(url);
    URL.revokeObjectURL(url);

    this.node = new AudioWorkletNode(this.ctx, 'pcm16k-processor');
    this.node.port.onmessage = (ev: MessageEvent<ArrayBuffer>) => {
      // Usually one full frame (3200 bytes); split when the tab stalls (api.md ≤64 KB).
      const data = new Uint8Array(ev.data);
      const frame = FRAME_BYTES;
      for (let off = 0; off + frame <= data.length; off += frame) {
        this.onFrame?.(data.slice(off, off + frame).buffer);
      }
    };
    const source = this.ctx.createMediaStreamSource(this.stream);
    source.connect(this.node);
    this.node.connect(this.ctx.destination);
  }

  stop(): void {
    this.node?.port.close();
    this.node?.disconnect();
    this.stream?.getTracks().forEach((t) => t.stop());
    void this.ctx?.close();
    this.node = null;
    this.stream = null;
    this.ctx = null;
    this.onFrame = null;
  }
}
