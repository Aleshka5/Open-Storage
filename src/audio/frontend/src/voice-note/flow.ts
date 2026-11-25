// Voice note flow (US-05): a state machine from microphone to done.
// Pure logic without DOM/WebAudio — tested with a fake socket and a fake
// recorder. The React helper on top is useVoiceNote.ts.

export type MicState = 'idle' | 'recording' | 'finalizing';

export interface VoiceNoteSocket {
  send(data: ArrayBuffer | string): void;
  close(code?: number): void;
  onmessage: (frame: VoiceNoteServerFrame) => void;
  onclose: (code: number | null) => void;
  onerror: (code: string, message: string) => void;
}

export interface VoiceNoteRecorder {
  start(onFrame: (pcm: ArrayBuffer) => void): Promise<void>;
  stop(): void;
}

export interface VoiceNoteServerFrame {
  type: string;
  [key: string]: unknown;
}

export interface VoiceNoteFlowCallbacks {
  onPartial(text: string, endMs: number, revision: number): void;
  onFinal(text: string, endMs: number, revision: number): void;
  onDone(recordingId: string): void;
  onError(errorCode: string, message: string): void;
  onState(state: MicState): void;
  onDuration(durationMs: number): void;
}

/** A 100 ms PCM frame = 1600 samples × 2 bytes (api.md). */
export const FRAME_BYTES = 3200;

export class VoiceNoteFlow {
  state: MicState = 'idle';
  private recordingId = '';

  constructor(
    private socket: VoiceNoteSocket,
    private recorder: VoiceNoteRecorder,
    private cb: VoiceNoteFlowCallbacks,
  ) {
    socket.onmessage = (frame) => this.handleFrame(frame);
    socket.onclose = (code) => this.handleClose(code);
    socket.onerror = (code, message) => this.handleError(code, message);
  }

  async start(recordingId: string): Promise<void> {
    this.recordingId = recordingId;
    this.setState('recording');
    await this.recorder.start((pcm) => this.socket.send(pcm));
  }

  async stop(): Promise<void> {
    // Releasing the button → spinner, the socket is NOT closed (we wait for stopped/done).
    this.recorder.stop();
    this.setState('finalizing');
    this.socket.send(JSON.stringify({ type: 'stop' }));
  }

  private handleFrame(frame: VoiceNoteServerFrame): void {
    switch (frame.type) {
      case 'partial': {
        const endMs = Number(frame.end_ms ?? 0);
        this.cb.onPartial(String(frame.text ?? ''), endMs, Number(frame.revision ?? 0));
        this.cb.onDuration(endMs);
        break;
      }
      case 'final': {
        const endMs = Number(frame.end_ms ?? 0);
        this.cb.onFinal(String(frame.text ?? ''), endMs, Number(frame.revision ?? 0));
        this.cb.onDuration(endMs);
        break;
      }
      case 'done':
        // The button is a microphone again, the recording is ready, the player is available.
        this.setState('idle');
        this.cb.onDone(this.recordingId);
        break;
      default:
        break;
    }
  }

  private handleClose(code: number | null): void {
    // 1000 — normal completion after done; anything else is an error (4408 idle etc.).
    if (code !== null && code !== 1000) {
      const err = code === 4503 ? 'ASR_BUSY' : code === 4408 ? 'IDLE_TIMEOUT' : 'STREAM_CLOSED';
      this.cb.onError(err, `Connection closed (${code})`);
      this.setState('idle');
    }
  }

  private handleError(code: string, message: string): void {
    this.cb.onError(code, message);
    this.setState('idle');
  }

  private setState(s: MicState): void {
    if (this.state !== s) {
      this.state = s;
      this.cb.onState(s);
    }
  }
}
