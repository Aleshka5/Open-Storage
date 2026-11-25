// The "Make it my voice" item (US-07, design_document.md §«Speaker menu», item 4).
//
// One component for two entry points:
//  - a recording's speaker — `speakerId` is set, the vector comes from `speakers.centroid`;
//  - a note — `speakerId` is null, the vector comes from `recordings.voice_embedding`.
//
// Inactive with a hint while `processing.embedding !== 'ready'` (queue-audio-embedding
// /message.md §«While the vector is missing»): the note plays, but there is no voice yet. A short
// note (`embedding.failed`, `too_short`) stays inactive — the server would answer 409
// VOICE_NOT_READY, and the UI must not call it for nothing.
//
// Contract errors: 409 VOICE_NOT_READY → the same "Voice is still being processed" hint;
// 503 VOICE_INDEX_INCOMPATIBLE → "Voice is incompatible with the index"; 404 → "Recording not found".

import { useState } from 'react';
import { setMeVoice } from './api';
import { isVoiceReady, type EmbeddingState } from './embedding';

export interface MakeMeVoiceProps {
  recordingId: string;
  /** The recording's speaker; null means the voice comes from the note. */
  speakerId: string | null;
  /** The recording's `processing.embedding`; `undefined` means unknown state (treated as pending). */
  embedding: EmbeddingState | undefined;
  /** Called after a successful replacement so the UI shows "Me" in the sidebar without a reload. */
  onDone?: (result: { label: 'Me'; has_default_voice: boolean }) => void;
  /** Interface strings can be overridden (the defaults are the English literals). */
  strings?: Partial<MakeMeVoiceStrings>;
}

export interface MakeMeVoiceStrings {
  action: string;
  pending: string;
  done: string;
  incompatible: string;
  notFound: string;
  failed: string;
}

const DEFAULT_STRINGS: MakeMeVoiceStrings = {
  action: 'Make it my voice',
  pending: 'Voice is still being processed',
  done: 'This is your voice',
  incompatible: 'Voice is incompatible with the voice index',
  notFound: 'Recording not found',
  failed: 'Could not apply the voice',
};

export function MakeMeVoiceButton({
  recordingId,
  speakerId,
  embedding,
  onDone,
  strings: override,
}: MakeMeVoiceProps) {
  const s = { ...DEFAULT_STRINGS, ...override };
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState(false);

  const ready = isVoiceReady(embedding);
  const hint = ready ? null : s.pending;

  const run = async () => {
    if (!ready || busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await setMeVoice({ recording_id: recordingId, speaker_id: speakerId ?? null });
      setDone(true);
      onDone?.({ label: 'Me', has_default_voice: res.has_default_voice });
    } catch (e) {
      const err = e as Error & { status?: number; error_code?: string };
      if (err.error_code === 'VOICE_NOT_READY') setError(s.pending);
      else if (err.error_code === 'VOICE_INDEX_INCOMPATIBLE') setError(s.incompatible);
      else if (err.status === 404) setError(s.notFound);
      else setError(s.failed);
    } finally {
      setBusy(false);
    }
  };

  return (
    <span className="make-me-voice">
      <button
        type="button"
        role="menuitem"
        className="speaker-menu-item speaker-menu-default"
        aria-disabled={!ready}
        disabled={!ready || busy}
        title={hint ?? s.action}
        onClick={() => void run()}
      >
        {s.action}
      </button>
      {hint && (
        <span className="make-me-voice-hint" data-hint="embedding-pending">
          {hint}
        </span>
      )}
      {done && !error && (
        <span className="make-me-voice-done" role="status">
          {s.done}
        </span>
      )}
      {error && (
        <span className="make-me-voice-error" role="alert">
          {error}
        </span>
      )}
    </span>
  );
}

export default MakeMeVoiceButton;
