// Adapts the browser WebSocket to the VoiceNoteSocket interface (flow.ts).

import type {
  VoiceNoteServerFrame,
  VoiceNoteSocket,
} from './flow';

export function openVoiceNoteSocket(url: string): VoiceNoteSocket {
  const ws = new WebSocket(url);
  const socket: VoiceNoteSocket = {
    send(data) {
      ws.send(data as string | ArrayBuffer);
    },
    close(code?: number) {
      ws.close(code);
    },
    onmessage() {
      /* overridden in flow */
    },
    onclose() {},
    onerror() {},
  };

  ws.onmessage = (ev) => {
    if (typeof ev.data === 'string') {
      try {
        socket.onmessage(JSON.parse(ev.data) as VoiceNoteServerFrame);
      } catch {
        /* ignore non-JSON */
      }
    }
  };
  ws.onclose = (ev) => socket.onclose(ev.code ?? null);
  ws.onerror = () => socket.onerror('NETWORK', 'Connection lost');

  return socket;
}
