// Voice note state-machine test (US-05) — without DOM/WebAudio.

import { describe, expect, it, vi } from 'vitest';
import { VoiceNoteFlow, type VoiceNoteRecorder, type VoiceNoteServerFrame, type VoiceNoteSocket } from './flow';

function fakeSocket() {
  const sent: (ArrayBuffer | string)[] = [];
  const socket: VoiceNoteSocket = {
    send: (d) => sent.push(d),
    close: vi.fn(),
    onmessage: () => {},
    onclose: () => {},
    onerror: () => {},
  };
  return { socket, sent };
}

function fakeRecorder() {
  let onFrame: ((pcm: ArrayBuffer) => void) | null = null;
  const recorder: VoiceNoteRecorder = {
    start: async (cb) => { onFrame = cb; },
    stop: () => { onFrame = null; },
  };
  return { recorder, emit: (pcm: ArrayBuffer) => onFrame?.(pcm) };
}

function callbacks() {
  return {
    onPartial: vi.fn(),
    onFinal: vi.fn(),
    onDone: vi.fn(),
    onError: vi.fn(),
    onState: vi.fn(),
    onDuration: vi.fn(),
  };
}

describe('VoiceNoteFlow', () => {
  it('microphone → pulse → spinner → microphone', async () => {
    const { socket, sent } = fakeSocket();
    const { recorder } = fakeRecorder();
    const cb = callbacks();
    const flow = new VoiceNoteFlow(socket, recorder, cb);

    await flow.start('rec-1');
    expect(cb.onState).toHaveBeenLastCalledWith('recording');

    await flow.stop();
    expect(cb.onState).toHaveBeenLastCalledWith('finalizing');
    expect(JSON.parse(sent[sent.length - 1] as string)).toEqual({ type: 'stop' });

    // done → idle again.
    socket.onmessage({ type: 'done' } as VoiceNoteServerFrame);
    expect(cb.onState).toHaveBeenLastCalledWith('idle');
    expect(cb.onDone).toHaveBeenCalledWith('rec-1');
  });

  it('partial forwards the growing text with its revision', async () => {
    const { socket } = fakeSocket();
    const { recorder } = fakeRecorder();
    const cb = callbacks();
    const flow = new VoiceNoteFlow(socket, recorder, cb);
    await flow.start('rec-1');

    socket.onmessage({ type: 'partial', text: 'hello', end_ms: 2400, revision: 3 } as VoiceNoteServerFrame);
    expect(cb.onPartial).toHaveBeenCalledWith('hello', 2400, 3);
    expect(cb.onDuration).toHaveBeenCalledWith(2400);
  });

  it('4503 → ASR_BUSY toast and the button returns', async () => {
    const { socket } = fakeSocket();
    const { recorder } = fakeRecorder();
    const cb = callbacks();
    const flow = new VoiceNoteFlow(socket, recorder, cb);
    await flow.start('rec-1');

    socket.onclose(4503);
    expect(cb.onError).toHaveBeenCalledWith('ASR_BUSY', expect.stringContaining('4503'));
    expect(cb.onState).toHaveBeenLastCalledWith('idle');
  });

  it('4408 idle → error and the button returns', async () => {
    const { socket } = fakeSocket();
    const { recorder } = fakeRecorder();
    const cb = callbacks();
    const flow = new VoiceNoteFlow(socket, recorder, cb);
    await flow.start('rec-1');

    socket.onclose(4408);
    expect(cb.onError).toHaveBeenCalledWith('IDLE_TIMEOUT', expect.stringContaining('4408'));
  });

  it('PCM frames go to the socket during capture', async () => {
    const { socket, sent } = fakeSocket();
    const { recorder, emit } = fakeRecorder();
    const cb = callbacks();
    const flow = new VoiceNoteFlow(socket, recorder, cb);
    await flow.start('rec-1');

    const pcm = new Uint8Array(3200).buffer;
    emit(pcm);
    expect(sent).toContain(pcm);
  });
});
