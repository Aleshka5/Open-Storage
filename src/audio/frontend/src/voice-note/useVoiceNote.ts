// React helper on top of VoiceNoteFlow: manages the note's lifecycle.

import { useCallback, useRef, useState } from 'react';
import { createVoiceNote, voiceNoteStreamUrl } from '../api/client';
import type { VoiceNoteCreated } from '../api/types';
import { VoiceNoteFlow, type MicState } from './flow';
import { openVoiceNoteSocket } from './ws';
import { WorkletRecorder } from './recorder';

export interface VoiceNoteControls {
  state: MicState;
  durationMs: number;
  partialText: string;
  start: () => Promise<void>;
  stop: () => Promise<void>;
}

interface Handlers {
  /** The note recording was created — the UI can switch to it and watch the text grow. */
  onStart?: (created: VoiceNoteCreated) => void;
  onDone?: (created: VoiceNoteCreated) => void;
  onError?: (errorCode: string, message: string) => void;
}

export function useVoiceNote(handlers: Handlers = {}): VoiceNoteControls {
  const [state, setState] = useState<MicState>('idle');
  const [durationMs, setDurationMs] = useState(0);
  const [partialText, setPartialText] = useState('');
  const flowRef = useRef<VoiceNoteFlow | null>(null);
  const createdRef = useRef<VoiceNoteCreated | null>(null);
  const handlersRef = useRef(handlers);
  handlersRef.current = handlers;

  const start = useCallback(async () => {
    const created = await createVoiceNote();
    createdRef.current = created;
    if (handlersRef.current.onStart) handlersRef.current.onStart(created);
    const socket = openVoiceNoteSocket(voiceNoteStreamUrl(created.ws_url));
    const flow = new VoiceNoteFlow(socket, new WorkletRecorder(), {
      onPartial: (text) => setPartialText(text),
      onFinal: (text) => setPartialText(text),
      onDone: () => {
        if (createdRef.current && handlersRef.current.onDone) {
          handlersRef.current.onDone(createdRef.current);
        }
      },
      onError: (code, message) => {
        if (handlersRef.current.onError) handlersRef.current.onError(code, message);
      },
      onState: (s) => setState(s),
      onDuration: (ms) => setDurationMs(ms),
    });
    flowRef.current = flow;
    setPartialText('');
    setDurationMs(0);
    await flow.start(created.recording_id);
  }, []);

  const stop = useCallback(async () => {
    await flowRef.current?.stop();
  }, []);

  return { state, durationMs, partialText, start, stop };
}
