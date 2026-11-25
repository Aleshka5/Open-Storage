// Chat: phrases by seq, statuses, renaming, the active phrase. The scroll container
// is hoisted out (scrollRef) for auto-scroll by the five-second rule.

import { useState, type RefObject } from 'react';
import type { Phrase, RecordingDetail } from '../api/types';
import type { EmbeddingState } from '../me/embedding';
import { PhraseTile, type AssignedResult } from './PhraseTile';
import { humanizeErrorCode } from '../strings';

export interface ChatPaneProps {
  recording: RecordingDetail | null;
  phrases: Phrase[];
  activeSeq: number | null;
  progressText: string | null;
  scrollRef: RefObject<HTMLDivElement>;
  handleUserScroll: () => void;
  onRename: (title: string) => void;
  onPhraseAssigned: (speakerId: string, result: AssignedResult) => void;
  /** "Me" voice replaced from a phrase menu (US-07). */
  onMeVoiceSet?: (result: { label: 'Me'; has_default_voice: boolean }) => void;
}

export function ChatPane({
  recording,
  phrases,
  activeSeq,
  progressText,
  scrollRef,
  handleUserScroll,
  onRename,
  onPhraseAssigned,
  onMeVoiceSet,
}: ChatPaneProps) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState('');

  const status = recording?.status ?? null;
  const failed = status === 'failed';
  const errorCode = recording?.processing?.error_code ?? null;
  // The recording's voice vector: the "Make it my voice" item waits for `ready` (US-07).
  const embedding = recording?.processing?.embedding as EmbeddingState | undefined;

  const startEdit = () => {
    setDraft(recording?.title ?? '');
    setEditing(true);
  };
  const commit = () => {
    const v = draft.trim();
    if (v.length > 0 && v !== recording?.title) onRename(v);
    setEditing(false);
  };

  return (
    <section className="chat-pane" aria-label="Chat">
      <header className="chat-header">
        {recording &&
          (editing ? (
            <form
              className="rename-form"
              onSubmit={(e) => {
                e.preventDefault();
                commit();
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                maxLength={120}
                aria-label="Recording title"
                autoFocus
              />
              <button type="submit" className="btn btn-small">
                Save
              </button>
            </form>
          ) : (
            <>
              <h1 className="chat-title">{recording.title}</h1>
              <button
                type="button"
                className="btn btn-ghost btn-small"
                onClick={startEdit}
                aria-label="Rename"
              >
                Rename
              </button>
            </>
          ))}
        {progressText && <span className="chat-progress">{progressText}</span>}
      </header>

      {failed && (
        <div className="error-banner" role="alert">
          Processing failed: {humanizeErrorCode(errorCode)}
        </div>
      )}

      <div className="chat-scroll" ref={scrollRef} onScroll={handleUserScroll}>
        {status === 'recording' && (
          <div className="chat-column">
            <p className="status-line">Recording… release the microphone to finish</p>
          </div>
        )}

        {status === 'diarizing' && (
          <div className="chat-column">
            <p className="status-line">Detecting voices…</p>
            <div className="skeleton" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {status === 'transcribing' && phrases.length === 0 && (
          <div className="chat-column">
            <p className="status-line">Transcribing speech…</p>
            <div className="skeleton" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
          </div>
        )}

        {phrases.length > 0 && (
          <ul className="chat-column" role="list">
            {phrases.map((p) => (
              <PhraseTile
                key={p.id}
                phrase={p}
                active={p.seq === activeSeq}
                recordingId={recording?.id ?? ''}
                onAssigned={onPhraseAssigned}
                embedding={embedding}
                onMeVoiceSet={onMeVoiceSet}
              />
            ))}
          </ul>
        )}

        {status === 'ready' && phrases.length === 0 && (
          <div className="empty-state">
            <p>This recording has no phrases yet.</p>
          </div>
        )}
      </div>
    </section>
  );
}
