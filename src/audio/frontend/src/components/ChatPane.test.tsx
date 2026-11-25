// A finished recording must show its text: the chat is the product. Regression guard for
// "the chat is available while processing and gone after ready".
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { createRef } from 'react';
import { ChatPane } from './ChatPane';
import type { Phrase, RecordingDetail } from '../api/types';

function recording(over: Partial<RecordingDetail> = {}): RecordingDetail {
  return {
    id: 'rec-1',
    title: 'Daily English',
    kind: 'upload',
    status: 'ready',
    duration_ms: 60000,
    language: 'en',
    is_default_voice: false,
    audio: { content_type: 'audio/wav', bytes: 1024 },
    processing: { error_code: null, phrases_done: 2, phrases_total: 2, embedding: 'none' },
    created_at: '2026-11-01T10:00:00Z',
    ready_at: '2026-11-01T10:01:00Z',
    ...over,
  };
}

const phrases: Phrase[] = [
  {
    id: 'p1',
    seq: 1,
    speaker_id: 's1',
    label: 'Speaker 1',
    side: 'left',
    start_ms: 0,
    end_ms: 1000,
    text: 'Hello there',
    state: 'final',
    revision: 0,
    overlap: false,
  },
  {
    id: 'p2',
    seq: 2,
    speaker_id: 's1',
    label: 'Speaker 1',
    side: 'left',
    start_ms: 1000,
    end_ms: 2000,
    text: 'General Kenobi',
    state: 'final',
    revision: 0,
    overlap: false,
  },
];

function renderPane(props: Partial<React.ComponentProps<typeof ChatPane>> = {}) {
  return render(
    <ChatPane
      recording={recording()}
      phrases={phrases}
      activeSeq={null}
      progressText={null}
      scrollRef={createRef<HTMLDivElement>()}
      handleUserScroll={() => {}}
      onRename={vi.fn()}
      onPhraseAssigned={vi.fn()}
      {...props}
    />,
  );
}

describe('ChatPane', () => {
  it('renders the phrases of a ready recording', () => {
    renderPane();
    expect(screen.getByText('Hello there')).toBeTruthy();
    expect(screen.getByText('General Kenobi')).toBeTruthy();
    expect(screen.queryByText('This recording has no phrases yet.')).toBeNull();
  });

  it('says so when a ready recording really has no phrases', () => {
    renderPane({ phrases: [] });
    expect(screen.getByText('This recording has no phrases yet.')).toBeTruthy();
  });

  it('shows the recording state while a note is being captured', () => {
    renderPane({ recording: recording({ kind: 'voice_note', status: 'recording' }), phrases: [] });
    expect(screen.getByText(/Recording…/)).toBeTruthy();
  });
});
