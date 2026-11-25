// Regression guard for «the UI disappears after an upload»: POST /api/recordings answers
// `201` with the recording object itself, NOT the `{recording, speakers}` envelope of
// GET /{id}. Reading it as `created.recording` threw inside the `setRecordings` updater —
// that is a render-phase error, so React unmounted the whole tree and the page went blank
// until a manual reload (api.md §«POST /api/recordings», chat-and-player/init.md item 3).
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import App from './App';
import { toListItem } from './core/list';
import * as client from './api/client';
import type { RecordingDetail } from './api/types';
import { ApiError } from './api/types';

vi.mock('./api/client', () => ({
  listRecordings: vi.fn(),
  getRecording: vi.fn(),
  renameRecording: vi.fn(),
  getPhrases: vi.fn(),
  uploadRecordingWithProgress: vi.fn(),
  uploadRecording: vi.fn(),
  audioUrl: (id: string) => `/api/recordings/${id}/audio`,
  createVoiceNote: vi.fn(),
  voiceNoteStreamUrl: (url: string) => url,
}));

/** A recording exactly as `POST /api/recordings` returns it: flat, no `speakers`. */
function uploaded(over: Partial<RecordingDetail> = {}): RecordingDetail {
  return {
    id: 'rec-upload-1',
    title: 'Lecture 4',
    kind: 'upload',
    status: 'uploaded',
    duration_ms: 4200,
    language: null,
    is_default_voice: false,
    audio: { content_type: 'audio/mpeg', bytes: 49004 },
    processing: { error_code: null, phrases_done: 0, phrases_total: 0, embedding: 'none' },
    created_at: '2026-11-01T14:11:21Z',
    ready_at: null,
    ...over,
  };
}

beforeEach(() => {
  vi.mocked(client.listRecordings).mockResolvedValue({ items: [], next_cursor: null });
  vi.mocked(client.getRecording).mockResolvedValue({ recording: uploaded(), speakers: [] });
  vi.mocked(client.getPhrases).mockResolvedValue({
    recording: { status: 'uploaded', processing: { phrases_done: 0, phrases_total: 0 } },
    items: [],
    next_after_seq: 0,
  });
});

describe('App — file upload', () => {
  it('takes the 201 body as the recording itself and keeps the interface alive', async () => {
    vi.mocked(client.uploadRecordingWithProgress).mockResolvedValue(uploaded());

    const { container } = render(<App />);
    const input = container.querySelector('input[type=file]') as HTMLInputElement;
    expect(input).toBeTruthy();

    fireEvent.change(input, {
      target: { files: [new File(['bytes'], 'lecture.mp3', { type: 'audio/mpeg' })] },
    });

    // The recording appears in the sidebar and opens in the chat, both from the 201 body.
    await waitFor(() => expect(screen.getAllByText('Lecture 4').length).toBeGreaterThanOrEqual(2));
    // Nothing was torn down: the upload control is still there (it was blank before the fix).
    expect(screen.getByText('Upload file')).toBeTruthy();
    expect(container.querySelector('.sidebar')).toBeTruthy();
    expect(document.body.textContent).not.toBe('');
  });

  it('flattens processing into the list progress pair', () => {
    const item = toListItem(
      uploaded({
        processing: { error_code: null, phrases_done: 3, phrases_total: 40, embedding: 'none' },
      }),
    );
    expect(item.id).toBe('rec-upload-1');
    expect(item.progress).toEqual({ phrases_done: 3, phrases_total: 40 });
    expect(item.title).toBe('Lecture 4');
  });

  it('survives an upload error without unmounting', async () => {
    vi.mocked(client.uploadRecordingWithProgress).mockRejectedValue(
      new ApiError(413, 'PAYLOAD_TOO_LARGE', 'File exceeds the allowed limit'),
    );

    const { container } = render(<App />);
    const input = container.querySelector('input[type=file]') as HTMLInputElement;
    fireEvent.change(input, {
      target: { files: [new File(['bytes'], 'big.mp3', { type: 'audio/mpeg' })] },
    });

    await waitFor(() =>
      expect(screen.getByRole('alert').textContent).toContain('File exceeds the allowed limit'),
    );
    expect(screen.getByText('Upload file')).toBeTruthy();
  });
});
