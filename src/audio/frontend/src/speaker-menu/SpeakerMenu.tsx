// Speaker menu (design_document.md §«Speaker menu»).
//
// Opens on a click on the phrase label. The `suggestions` request is sent ONLY on
// opening (ADR-007): not when the recording loads and not while scrolling. It contains:
//  1. the suggestion list (at most 5 nicknames + "Me" first when a voice exists), nothing selected;
//  2. a "New nickname" field with a "Create" button;
//  3. for an already assigned speaker, an explanation that it is irreversible (reassign → 409);
//  4. the "Make it my voice" item;
//  5. the "Suggestions unavailable" state on 503 VOICE_INDEX_UNAVAILABLE.
//
// Self-contained module: it does not pull in api/client.ts or the components/* branch of US-04.
// It is wired into the chat as <SpeakerMenuButton> in place of the phrase label (when US-04/US-06 merge).

import { useEffect, useRef, useState } from 'react';
import { MakeMeVoiceButton } from '../me/MakeMeVoiceButton';
import type { EmbeddingState } from '../me/embedding';
import { assignNick, fetchSuggestions } from './api';
import type { SpeakerRef, SuggestionItem } from './types';

export interface SpeakerMenuButtonProps {
  /** Speaker context (recording_id + speaker_id) and the current label. */
  speaker: SpeakerRef;
  /** Called after a successful assignment so the chat updates labels without a reload. */
  onAssigned: (result: { label: string; nick_id: string | null; is_me: boolean }) => void;
  /** Interface strings can be overridden (the defaults are the English literals). */
  strings?: Partial<SpeakerMenuStrings>;
  /**
   * The recording's `recordings.processing.embedding` (US-07): "Make it my voice" is inactive
   * until the vector is ready. `undefined` means the state is unknown (the item is inactive).
   */
  embedding?: EmbeddingState;
  /** After the "Me" voice is replaced (the sidebar / GET /api/me refresh without a reload). */
  onMeVoiceSet?: (result: { label: 'Me'; has_default_voice: boolean }) => void;
}

export interface SpeakerMenuStrings {
  title: string;
  newNick: string;
  create: string;
  makeDefault: string;
  makeDefaultPending: string;
  unavailable: string;
  assignmentLocked: string;
  currentLabel: string;
  reassign: string;
}

const DEFAULT_STRINGS: SpeakerMenuStrings = {
  title: 'Speaker voice',
  newNick: 'New nickname',
  create: 'Create',
  makeDefault: 'Make it my voice',
  makeDefaultPending: 'Voice is still being processed',
  unavailable: 'Suggestions unavailable',
  assignmentLocked: 'Speaker is already assigned: splitting is not supported',
  currentLabel: 'Current label',
  reassign: 'Assign again',
};

export function SpeakerMenuButton({
  speaker,
  onAssigned,
  strings: override,
  embedding,
  onMeVoiceSet,
}: SpeakerMenuButtonProps) {
  const s = { ...DEFAULT_STRINGS, ...override };
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<SuggestionItem[]>([]);
  const [unavailable, setUnavailable] = useState(false);
  const [loading, setLoading] = useState(false);
  const [newName, setNewName] = useState('');
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  // Suggestions are fetched only when the menu opens (ADR-007); reopening issues a new request.
  useEffect(() => {
    if (!open) return;
    let cancelled = false;
    setLoading(true);
    setUnavailable(false);
    setError(null);
    void fetchSuggestions(speaker.recording_id, speaker.speaker_id)
      .then((res) => {
        if (cancelled) return;
        setItems(res.items);
      })
      .catch((e: Error & { status?: number }) => {
        if (cancelled) return;
        if (e.status === 503) setUnavailable(true);
        else setError(e.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [open, speaker.recording_id, speaker.speaker_id]);

  // Close on a click outside the menu.
  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDoc);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  const run = async (body: Parameters<typeof assignNick>[2]) => {
    try {
      const res = await assignNick(speaker.recording_id, speaker.speaker_id, body);
      onAssigned({
        label: res.speaker.label,
        nick_id: res.speaker.nick_id,
        is_me: res.speaker.is_me,
      });
      setOpen(false);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const submitNew = (e: React.FormEvent) => {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    void run({ name });
  };

  const alreadyAssigned = speaker.nick_id != null || speaker.is_me;

  return (
    <span className="speaker-menu" ref={rootRef}>
      <button
        type="button"
        className="speaker-menu-label"
        onClick={() => setOpen(o => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
      >
        {speaker.label}
      </button>

      {open && (
        <div className="speaker-menu-pop" role="menu">
          <div className="speaker-menu-title">{s.title}</div>

          {loading && <div className="speaker-menu-status">…</div>}

          {!loading && unavailable && (
            <div className="speaker-menu-status" data-unavailable>
              {s.unavailable}
            </div>
          )}

          {!loading && error && (
            <div className="speaker-menu-status" role="alert">
              {error}
            </div>
          )}

          {!loading && !unavailable && !error && items.length > 0 && (
            <ul className="speaker-menu-list" role="none">
              {items.map((item) =>
                item.kind === 'me' ? (
                  <li key="me" role="none">
                    <button
                      type="button"
                      role="menuitem"
                      className="speaker-menu-item"
                      onClick={() => void run({ me: true })}
                    >
                      Me
                    </button>
                  </li>
                ) : (
                  <li key={item.nick_id} role="none">
                    <button
                      type="button"
                      role="menuitem"
                      className="speaker-menu-item"
                      onClick={() => void run({ nick_id: item.nick_id })}
                    >
                      {item.name}
                    </button>
                  </li>
                ),
              )}
            </ul>
          )}

          {alreadyAssigned && (
            <div className="speaker-menu-locked" role="note">
              {s.assignmentLocked}
            </div>
          )}

          {!speaker.is_me && (
            <form className="speaker-menu-new" onSubmit={submitNew}>
              <input
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder={s.newNick}
                maxLength={120}
                aria-label={s.newNick}
              />
              <button type="submit" className="btn btn-small" disabled={!newName.trim()}>
                {s.create}
              </button>
            </form>
          )}

          {/* "Make it my voice" replaces the "Me" voice (PUT /api/me/voice) rather than
              assigning a speaker label: labels of past chats do not change (ADR-008). */}
          <MakeMeVoiceButton
            recordingId={speaker.recording_id}
            speakerId={speaker.speaker_id}
            embedding={embedding}
            onDone={onMeVoiceSet}
            strings={{ action: s.makeDefault, pending: s.makeDefaultPending }}
          />
        </div>
      )}
    </span>
  );
}

export default SpeakerMenuButton;
