// Chat phrase tile (design_document.md §«Phrase tile»).
// The speaker label is clickable: it opens the speaker menu (US-06). After assignment
// the label is updated through `onAssigned` without reloading the page.

import type { Phrase } from '../api/types';
import { formatTime } from '../strings';
import type { EmbeddingState } from '../me/embedding';
import { SpeakerMenuButton } from '../speaker-menu/SpeakerMenu';
import type { SpeakerRef } from '../speaker-menu/types';

export interface AssignedResult {
  label: string;
  nick_id: string | null;
  is_me: boolean;
}

export interface PhraseTileProps {
  phrase: Phrase;
  active: boolean;
  recordingId: string;
  onAssigned: (speakerId: string, result: AssignedResult) => void;
  /** The recording's `processing.embedding`: gates the "Make it my voice" item (US-07). */
  embedding?: EmbeddingState;
  /** "Me" voice replaced — the UI refreshes "Me" in the menu without a reload. */
  onMeVoiceSet?: (result: { label: 'Me'; has_default_voice: boolean }) => void;
}

export function PhraseTile({
  phrase,
  active,
  recordingId,
  onAssigned,
  embedding,
  onMeVoiceSet,
}: PhraseTileProps) {
  const cls = [
    'phrase',
    phrase.side === 'right' ? 'side-right' : 'side-left',
    phrase.state === 'partial' ? 'state-partial' : '',
    active ? 'is-active' : '',
  ]
    .filter(Boolean)
    .join(' ');

  const speaker: SpeakerRef = {
    recording_id: recordingId,
    speaker_id: phrase.speaker_id,
    label: phrase.label,
    is_me: phrase.label === 'Me',
    nick_id: null,
  };

  return (
    <li
      className={cls}
      aria-current={active ? 'true' : undefined}
      data-seq={phrase.seq}
    >
      <div className="phrase-meta">
        <SpeakerMenuButton
          speaker={speaker}
          onAssigned={(result) => onAssigned(phrase.speaker_id, result)}
          embedding={embedding}
          onMeVoiceSet={onMeVoiceSet}
        />
        <span className="phrase-time">{formatTime(phrase.start_ms)}</span>
      </div>
      {/* Read-only: no contenteditable and no input fields. */}
      <span className="phrase-text">{phrase.text}</span>
    </li>
  );
}
